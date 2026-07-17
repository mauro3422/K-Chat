"""HTTP endpoints for memory maintenance and sync."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.memory import memory_graph_snapshot
from src.gateway_log import log_event
from web.routers._memory_snapshot import (
    build_memory_snapshot,
    summarize_memory_compare,
    _get_lease_manager,
    _get_manage_memory_run,
    _get_repos,
)
from web.routers._node_helpers import _get_coordinator, _get_event_bus
from web.services.lan_auth import require_lan_request

router = APIRouter(
    prefix="/api/memory",
    dependencies=[Depends(require_lan_request)],
)


class MemoryMaintenancePayload(BaseModel):
    dry_run: bool = Field(default=False)
    confirm: bool = Field(default=False)
    key_pattern: str = Field(default="", max_length=512)
    fmt: str = Field(default="text", max_length=32)


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
async def get_graph(request: Request, layer: str = "unified", limit: int = 100) -> JSONResponse:
    cache = getattr(request.app.state, "memory_graph_cache", {})
    now = time.monotonic()
    safe_limit = max(10, min(limit, 300))
    cache_key = f"{layer}:{safe_limit}"
    cached = cache.get(cache_key)
    if cached and now - cached["created_at"] < 30:
        return JSONResponse(cached["payload"], headers={"X-Graph-Cache": "hit"})
    payload = memory_graph_snapshot(layer=layer, node_limit=safe_limit)
    cache[cache_key] = {"created_at": now, "payload": payload}
    request.app.state.memory_graph_cache = cache
    return JSONResponse(payload, headers={"X-Graph-Cache": "miss"})
