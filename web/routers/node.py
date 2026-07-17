"""LAN node coordination endpoints.

Split from the original 519-line god router into three focused routers
(``node.py``, ``node_memory.py``, ``node_failover.py``) plus shared helpers in
``_node_helpers.py`` and observability logic in ``web/services/node_observability.py``.
URLs unchanged — all routers share the ``/api/node`` prefix and are wired up by
auto-discovery in ``app_factory.register_routers``.

This module keeps the *coordination* domain:
    GET  /state        — coordinator snapshot
    GET  /runtime      — runtime + memory + failover observability
    POST /heartbeat    — local beat or peer heartbeat registration
    POST /promote      — manual promote to primary, flushes memory queue
    POST /demote       — release leadership
    POST /event        — relay a memory/coord event to the bus
    GET  /sessions     — federated local session directory
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.coordination.memory_write_queue import apply_pending_memory_writes
from src.gateway_log import log_event
from src.coordination.lan_discovery import normalize_lan_peer_url
from web.routers._memory_snapshot import relay_memory_event
from web.routers._node_helpers import (
    _get_coordinator,
    _get_event_bus,
    _get_failover_state,
    _get_leader_lease_manager,
    _get_memory_queue,
    _get_node_bridge,
    _get_save_memory_run,
    _peer_cluster_state,
    _request_base_url,
    _request_repos,
)
from web.routers._node_models import NodeEventPayload, NodeHeartbeatPayload
from web.services.node_observability import _memory_observability, _memory_write_mode, _runtime_mode
from web.services.lan_auth import enforce_lan_node_identity, require_lan_request
from web.services.session_directory import session_summary_from_row

router = APIRouter(prefix="/api/node")


@router.get("/sessions", dependencies=[Depends(require_lan_request)])
async def node_sessions(request: Request, limit: int = 50) -> JSONResponse:
    coordinator = _get_coordinator(request)
    repos = _request_repos(request)
    raw = await repos.sessions.get_all(limit)
    snapshot = coordinator.snapshot()
    sessions = [
        session_summary_from_row(
            row,
            node_id=snapshot.get("node_id", coordinator.node_id),
            node_role=snapshot.get("role", coordinator.role),
            cluster_name=snapshot.get("cluster_name", coordinator.cluster_name),
            node_platform=snapshot.get("node_platform", ""),
            source_url=_request_base_url(request),
            source_mode="local",
        )
        for row in raw
    ]
    return JSONResponse({
        "ok": True,
        "node": snapshot,
        "sessions": sessions,
        "returned": len(sessions),
        "total": len(sessions),
    })


@router.get("/state")
async def node_state(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    snapshot = coordinator.snapshot()
    snapshot["local_peer_count"] = len(snapshot.get("peers", []))
    config = getattr(request.app.state, "config", None)
    snapshot["preferred_role"] = str(getattr(config, "node_role", "secondary"))
    return JSONResponse(snapshot)


@router.get("/runtime")
async def node_runtime(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    snapshot = coordinator.snapshot()
    config = getattr(request.app.state, "config", None)
    snapshot["preferred_role"] = str(getattr(config, "node_role", "secondary"))
    snapshot["local_peer_count"] = len(snapshot.get("peers", []))

    bridge = _get_node_bridge(request)
    queue = _get_memory_queue(request)
    lease_manager = _get_leader_lease_manager(request)
    cluster = await _peer_cluster_state(request)
    failover = _get_failover_state(request).snapshot()
    queue_size = len(queue)
    lease = lease_manager.snapshot()
    now = time.time()
    mode, reasons = _runtime_mode(snapshot, cluster, queue_size, failover)

    return JSONResponse(
        {
            "ok": mode == "normal",
            "mode": mode,
            "reasons": reasons,
            "node": {
                "node_id": snapshot.get("node_id", ""),
                "role": snapshot.get("role", ""),
                "preferred_role": snapshot.get("preferred_role", ""),
                "platform": snapshot.get("node_platform", ""),
                "cluster_name": snapshot.get("cluster_name", ""),
                "healthy": snapshot.get("healthy", False),
            },
            "bridge": {
                "base_url": bridge.base_url,
                "peer_urls": bridge.peer_urls,
            },
            "peers": {
                "configured": cluster.get("peer_count", 0),
                "reachable": cluster.get("reachable_peers", 0),
                "unreachable": cluster.get("unreachable_peers", 0),
                "states": cluster.get("states", []),
                "errors": cluster.get("errors", []),
            },
            "memory": {
                "is_fresh": snapshot.get("memory_is_fresh", False),
                "last_revision": snapshot.get("last_memory_revision", 0.0),
                "last_sync": snapshot.get("last_memory_sync", 0.0),
                "queue_size": queue_size,
                "queue_path": getattr(queue, "persistence_path", ""),
                "lease": lease.to_dict() if lease else None,
                "write": _memory_write_mode(snapshot, mode),
                "observability": _memory_observability(snapshot, queue, lease, now),
            },
            "failover": {
                "should_promote": failover.get("should_promote", False),
                "miss_count": failover.get("miss_count", 0),
                "required_misses": failover.get("required_misses", 0),
                "last_action": failover.get("last_action", ""),
                "last_reason": failover.get("last_reason", ""),
            },
        }
    )


@router.post("/heartbeat", dependencies=[Depends(require_lan_request)])
async def node_heartbeat(payload: NodeHeartbeatPayload, request: Request) -> JSONResponse:
    enforce_lan_node_identity(request, payload.node_id)
    coordinator = _get_coordinator(request)
    if payload.node_id:
        peer_url = normalize_lan_peer_url(payload.base_url)
        if peer_url:
            _get_node_bridge(request).register_discovered_peer(peer_url)
        snapshot = await coordinator.record_peer_heartbeat(
            node_id=payload.node_id,
            role=payload.role,
            base_url=peer_url or "",
            metadata=payload.metadata,
        )
    else:
        snapshot = await coordinator.beat(metadata=payload.metadata)
    config = getattr(request.app.state, "config", None)
    snapshot["preferred_role"] = str(getattr(config, "node_role", "secondary"))
    return JSONResponse({"ok": True, "state": snapshot})


@router.post("/promote", dependencies=[Depends(require_lan_request)])
async def node_promote(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    lease_manager = _get_leader_lease_manager(request)
    lease = lease_manager.acquire(coordinator.node_id, ttl=coordinator.heartbeat_ttl, reason="manual_promote")
    if lease is None:
        return JSONResponse({"ok": False, "error": "leader lease busy"}, status_code=409)
    snapshot = await coordinator.promote()
    applied = await apply_pending_memory_writes(
        _get_memory_queue(request),
        _get_save_memory_run(request),
        repos=getattr(request.app.state, "repos", None),
    )
    if applied:
        await coordinator.mark_memory_sync({"event": "node_promote", "applied": len(applied)})
    await _get_event_bus(request).publish("leader_changed", {"role": "primary", "state": snapshot})
    log_event("INFO", "node", "promote", detail="node promoted to primary", meta={"applied": len(applied)})
    return JSONResponse({"ok": True, "state": snapshot, "applied": applied})


@router.post("/demote", dependencies=[Depends(require_lan_request)])
async def node_demote(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    lease_manager = _get_leader_lease_manager(request)
    lease_manager.release(coordinator.node_id)
    snapshot = await coordinator.demote()
    await _get_event_bus(request).publish("leader_changed", {"role": "secondary", "state": snapshot})
    log_event("INFO", "node", "demote", detail="node demoted to secondary")
    return JSONResponse({"ok": True, "state": snapshot})


@router.post("/event", dependencies=[Depends(require_lan_request)])
async def node_event(payload: NodeEventPayload, request: Request) -> JSONResponse:
    enforce_lan_node_identity(request, str(payload.source.get("node_id", "")))
    await relay_memory_event(request, payload.type, {"data": payload.data, "source": payload.source})
    return JSONResponse({"ok": True, "type": payload.type})
