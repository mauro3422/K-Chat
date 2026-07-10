"""HTTP endpoints for memory maintenance and sync."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.gateway_log import log_event
from web.routers._memory_snapshot import (
    build_memory_snapshot,
    summarize_memory_compare,
    _get_lease_manager,
    _get_manage_memory_run,
    _get_repos,
)
from web.routers._node_helpers import _get_coordinator, _get_event_bus

router = APIRouter(prefix="/api/memory")


class MemoryMaintenancePayload(BaseModel):
    dry_run: bool = Field(default=False)
    confirm: bool = Field(default=False)
    key_pattern: str = Field(default="")
    fmt: str = Field(default="text")


@router.get("/compare")
async def compare(request: Request, key_pattern: str = "", fmt: str = "text") -> JSONResponse:
    result = await _get_manage_memory_run(request)(
        operation="compare",
        key_pattern=key_pattern,
        fmt=fmt,
        _repos=_get_repos(request),
    )
    parsed = None
    if fmt == "json":
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            parsed = {"raw": result}
    payload = {"ok": True, "result": result}
    if parsed is not None:
        payload["compare"] = parsed
    return JSONResponse(payload)


@router.get("/diagnostics")
async def diagnostics(request: Request, key_pattern: str = "") -> JSONResponse:
    return JSONResponse(await build_memory_snapshot(request, key_pattern=key_pattern))


@router.get("/conflicts")
async def conflicts(request: Request, key_pattern: str = "") -> JSONResponse:
    snapshot = await build_memory_snapshot(request, key_pattern=key_pattern)
    return JSONResponse(
        {
            "ok": True,
            "key_pattern": key_pattern,
            "compare": snapshot.get("compare", {}),
            "summary": summarize_memory_compare(snapshot.get("compare", {})),
            "memory": snapshot.get("memory", {}),
            "queue": {
                "size": snapshot.get("queue_size", 0),
                "pending": snapshot.get("queue", []),
                "path": snapshot.get("queue_path", ""),
            },
        }
    )


@router.get("/status")
async def status(request: Request) -> JSONResponse:
    lease_manager = _get_lease_manager(request)
    lease = lease_manager.snapshot()
    queue = getattr(request.app.state, "memory_write_queue", None)
    if queue is None:
        from src.coordination.memory_write_queue import get_memory_write_queue

        queue = get_memory_write_queue()
    return JSONResponse(
        {
            "ok": True,
            "lease": lease.to_dict() if lease else None,
            "queue_size": len(queue),
            "queue": queue.snapshot(),
            "queue_path": getattr(queue, "persistence_path", ""),
        }
    )


@router.post("/sync")
async def sync(payload: MemoryMaintenancePayload, request: Request) -> JSONResponse:
    result = await _get_manage_memory_run(request)(
        operation="sync",
        dry_run=payload.dry_run,
        confirm=payload.confirm,
        key_pattern=payload.key_pattern,
        _repos=_get_repos(request),
    )
    if not payload.dry_run:
        coordinator = _get_coordinator(request)
        await coordinator.mark_memory_sync({"event": "memory_sync"})
        await _get_event_bus(request).publish("memory_synced", {"source": "api", "operation": "sync", "result": result})
        log_event("INFO", "memory", "sync", detail="memory sync completed", meta={"operation": "sync", "result": result})
    return JSONResponse({"ok": True, "result": result})


@router.post("/repair")
async def repair(payload: MemoryMaintenancePayload, request: Request) -> JSONResponse:
    result = await _get_manage_memory_run(request)(
        operation="repair",
        dry_run=payload.dry_run,
        confirm=payload.confirm,
        key_pattern=payload.key_pattern,
        _repos=_get_repos(request),
    )
    if not payload.dry_run:
        coordinator = _get_coordinator(request)
        await coordinator.mark_memory_sync({"event": "memory_repair"})
        await _get_event_bus(request).publish("memory_synced", {"source": "api", "operation": "repair", "result": result})
        log_event("INFO", "memory", "sync", detail="memory repair completed", meta={"operation": "repair", "result": result})
    return JSONResponse({"ok": True, "result": result})


@router.get("/graph")
async def get_graph(request: Request, layer: str = "unified") -> JSONResponse:
    from src.memory.analysis.graph_analysis import EntityGraph
    from src.memory.memory_db_path import resolve_memory_db_path
    import sqlite3
    import logging

    local_logger = logging.getLogger(__name__)
    db_path = resolve_memory_db_path()
    graph = EntityGraph(db_path)
    graph.refresh()

    pmi_names = {
        name.lower()
        for ent_id, name in graph._names.items()
        if ent_id.startswith("pmi_")
    }

    exclude_pmi = (layer == "curated")
    only_pmi = (layer == "pmi")

    nodes = []
    for name in graph._degree_centrality.keys():
        name_lower = name.lower()
        is_pmi = name_lower in pmi_names

        if exclude_pmi and is_pmi:
            continue
        if only_pmi and not is_pmi:
            continue

        nodes.append({
            "id": name,
            "label": name.capitalize(),
            "pagerank": round(graph.pagerank(name), 6),
            "degree": round(graph.degree_centrality(name), 6),
            "hub": round(graph.hub_score(name), 6),
            "authority": round(graph.authority_score(name), 6),
            "community": graph.entity_community(name),
            "is_pmi": is_pmi
        })

    # Limitar el grafo a los 100 nodos más importantes por PageRank para rendimiento de D3
    nodes.sort(key=lambda x: x["pagerank"], reverse=True)
    nodes = nodes[:100]

    allowed_nodes = {n["id"].lower() for n in nodes}
    edges = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT source_id, target_id, weight FROM entity_relations"
        ):
            src = str(row["source_id"])
            tgt = str(row["target_id"])
            wt = float(row["weight"] or 1.0)
            src_name = graph._names.get(src)
            tgt_name = graph._names.get(tgt)
            if src_name and tgt_name:
                src_lower = src_name.lower()
                tgt_lower = tgt_name.lower()
                if src_lower in allowed_nodes and tgt_lower in allowed_nodes:
                    edges.append({
                        "source": src_lower,
                        "target": tgt_lower,
                        "weight": wt
                    })
        conn.close()
    except Exception as exc:
        local_logger.warning("Failed to load edges for API: %s", exc)

    return JSONResponse({
        "ok": True,
        "nodes": nodes,
        "edges": edges
    })
