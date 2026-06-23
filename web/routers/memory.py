"""HTTP endpoints for memory maintenance and sync."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.gateway_log import log_event
from src.coordination.memory_lease import get_memory_lease_manager
from src.coordination.node_state import get_node_coordinator
from web.routers._memory_snapshot import build_memory_snapshot, summarize_memory_compare
from web.services.event_bus import get_event_bus

router = APIRouter(prefix="/api/memory")


class MemoryMaintenancePayload(BaseModel):
    dry_run: bool = Field(default=False)
    confirm: bool = Field(default=False)
    key_pattern: str = Field(default="")
    fmt: str = Field(default="text")


def _get_repos(request: Request):
    return getattr(request.app.state, "repos", None)


def _get_manage_memory_run(request: Request):
    runner = getattr(request.app.state, "manage_memory_run", None)
    if runner is None:
        raise RuntimeError("manage_memory runner not configured")
    return runner


def _get_lease_manager(request: Request):
    return getattr(request.app.state, "memory_lease_manager", None) or get_memory_lease_manager(getattr(request.app.state, "config", None))


def _get_coordinator(request: Request):
    return getattr(request.app.state, "node_coordinator", None) or get_node_coordinator(getattr(request.app.state, "config", None))


def _get_event_bus(request: Request):
    return getattr(request.app.state, "event_bus", None) or get_event_bus()


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
