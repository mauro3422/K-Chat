"""LAN node memory coordination endpoints.

Split from ``node.py`` — keeps the distributed-memory domain (write queue,
lease-based snapshots, sync status, diagnostics). URLs unchanged, registered
under the same ``/api/node`` prefix via auto-discovery.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.coordination.memory_write_queue import apply_pending_memory_writes
from web.routers._memory_snapshot import build_memory_snapshot, relay_memory_event
from web.routers._node_helpers import (
    _get_coordinator,
    _get_event_bus,
    _get_leader_lease_manager,
    _get_memory_queue,
    _get_node_bridge,
    _get_save_memory_run,
    _peer_cluster_state,
)
from web.routers._node_models import NodeMemoryWritePayload
from web.services.node_observability import _memory_observability

router = APIRouter(prefix="/api/node")


@router.post("/memory/request")
async def memory_request(payload: NodeMemoryWritePayload, request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    config = getattr(request.app.state, "config", None)
    preferred_role = str(getattr(config, "node_role", "secondary"))
    if not await coordinator.is_primary():
        queue = _get_memory_queue(request)
        queued = queue.enqueue(payload.key, payload.value, source_node=str(payload.source.get("node_id", "")), reason="primary_unavailable")
        await _get_event_bus(request).publish(
            "memory_write_queued",
            {"key": payload.key, "source": payload.source, "state": queue.snapshot()},
        )
        return JSONResponse({"ok": True, "granted": False, "queued": True, "request": queued.to_dict()})

    started = time.perf_counter()
    result = await _get_save_memory_run(request)(
        key=payload.key,
        value=payload.value,
        _repos=getattr(request.app.state, "repos", None),
        _force_local_write=True,
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    if result.startswith("[OK]"):
        replay_request = None
        if preferred_role != "primary":
            queue = _get_memory_queue(request)
            replay_request = queue.enqueue(
                payload.key,
                payload.value,
                source_node=coordinator.node_id,
                reason="failover_replay_to_preferred_primary",
            )
        await coordinator.mark_memory_revision({"event": "memory_request", "key": payload.key})
        await coordinator.mark_memory_sync({"event": "memory_request", "key": payload.key})
        completion_event = {
            "key": payload.key,
            "value": payload.value,
            "source": payload.source,
            "node_id": coordinator.node_id,
            "result": result,
        }
        bus = _get_event_bus(request)
        await bus.publish("memory_synced", completion_event)
        await bus.publish("memory_write_completed", completion_event)
        try:
            bridge = _get_node_bridge(request)
            await bridge.broadcast_event("memory_write_completed", completion_event)
        except Exception:
            pass
    response = {"ok": True, "granted": True, "queued": False, "status": "completed", "duration_ms": duration_ms, "result": result}
    if result.startswith("[OK]") and preferred_role != "primary":
        response["replay_queued"] = True
        response["replay_request"] = replay_request.to_dict() if replay_request is not None else None
    return JSONResponse(response)


@router.get("/memory/queue")
async def memory_queue(request: Request) -> JSONResponse:
    queue = _get_memory_queue(request)
    return JSONResponse({"ok": True, "pending": queue.snapshot()})


@router.post("/memory/flush")
async def memory_flush(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    if not await coordinator.is_primary():
        return JSONResponse({"ok": False, "error": "primary only"}, status_code=403)

    results = await apply_pending_memory_writes(
        _get_memory_queue(request),
        _get_save_memory_run(request),
        repos=getattr(request.app.state, "repos", None),
    )
    if results:
        await _get_event_bus(request).publish("memory_synced", {"applied": results, "source": "flush"})
    return JSONResponse({"ok": True, "applied": results, "pending": []})


@router.get("/sync/status")
async def sync_status(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    queue = _get_memory_queue(request)
    lease_manager = _get_leader_lease_manager(request)
    lease = lease_manager.snapshot()
    bridge = _get_node_bridge(request)
    cluster = await _peer_cluster_state(request)
    snapshot = coordinator.snapshot()
    now = time.time()
    return JSONResponse(
        {
            "ok": True,
            "node": snapshot,
            "bridge": {
                "base_url": bridge.base_url,
                "peer_urls": bridge.peer_urls,
            },
            "cluster": cluster,
            "lease": lease.to_dict() if lease else None,
            "queue": {
                "size": len(queue),
                "pending": queue.snapshot(),
                "path": getattr(queue, "persistence_path", ""),
            },
            "sync": {
                "role": snapshot.get("role", ""),
                "is_primary": await coordinator.is_primary(),
                "has_recent_primary": snapshot.get("has_recent_primary", False),
                "memory_is_fresh": snapshot.get("memory_is_fresh", False),
                "last_memory_revision": snapshot.get("last_memory_revision", 0.0),
                "last_memory_sync": snapshot.get("last_memory_sync", 0.0),
            },
            "observability": _memory_observability(snapshot, queue, lease, now),
        }
    )


@router.get("/memory/snapshot")
async def memory_snapshot(request: Request, key_pattern: str = "") -> JSONResponse:
    coordinator = _get_coordinator(request)
    if await coordinator.is_primary():
        return JSONResponse(await build_memory_snapshot(request, key_pattern=key_pattern))

    bridge = _get_node_bridge(request)
    if bridge.peer_urls:
        remote = await bridge.request_memory_snapshot(key_pattern=key_pattern)
        if remote.get("ok"):
            payload = dict(remote.get("snapshot", {}))
            payload["source"] = {
                "mode": "peer",
                "peer": remote.get("peer"),
                "node_id": coordinator.node_id,
            }
            return JSONResponse(payload)

    return JSONResponse(await build_memory_snapshot(request, key_pattern=key_pattern))


@router.get("/diagnostics")
async def node_diagnostics(request: Request, key_pattern: str = "") -> JSONResponse:
    coordinator = _get_coordinator(request)
    bridge = _get_node_bridge(request)
    memory = await build_memory_snapshot(request, key_pattern=key_pattern)
    cluster = await _peer_cluster_state(request)
    payload = {
        "ok": True,
        "node": coordinator.snapshot(),
        "bridge": {
            "base_url": bridge.base_url,
            "peer_urls": bridge.peer_urls,
        },
        "cluster": cluster,
        "memory": memory,
    }
    return JSONResponse(payload)