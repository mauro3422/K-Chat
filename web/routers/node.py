"""LAN node coordination endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.repos import get_repos
from src.gateway_log import log_event
from src.coordination.leader_lease import get_leader_lease_manager
from src.coordination.memory_write_queue import apply_pending_memory_writes, get_memory_write_queue
from src.coordination.node_state import NodeCoordinator, get_node_coordinator
from src.coordination.lan_bridge import NodeLanBridge
from src.coordination.lan_discovery import normalize_lan_peer_url
from web.services.session_directory import session_summary_from_row
from web.routers._memory_snapshot import build_memory_snapshot, relay_memory_event
from web.services.event_bus import IEventBus, get_event_bus
from web.services.failover_state import get_failover_state

router = APIRouter(prefix="/api/node")


def _get_coordinator(request: Request) -> NodeCoordinator:
    return getattr(request.app.state, "node_coordinator", None) or get_node_coordinator(getattr(request.app.state, "config", None))


def _request_repos(request: Request):
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    repos = getattr(state, "repos", None) if state is not None else None
    return repos or get_repos()


def _get_event_bus(request: Request) -> IEventBus:
    return getattr(request.app.state, "event_bus", None) or get_event_bus()


def _get_memory_queue(request: Request):
    return getattr(request.app.state, "memory_write_queue", None) or get_memory_write_queue()


def _get_save_memory_run(request: Request):
    runner = getattr(request.app.state, "save_memory_run", None)
    if runner is None:
        raise RuntimeError("save_memory runner not configured")
    return runner


def _get_node_bridge(request: Request) -> NodeLanBridge:
    bridge = getattr(request.app.state, "node_bridge", None)
    if bridge is None:
        coordinator = _get_coordinator(request)
        config = getattr(request.app.state, "config", None)
        bridge = NodeLanBridge(config=config, coordinator=coordinator)
        request.app.state.node_bridge = bridge
    return bridge


def _get_leader_lease_manager(request: Request):
    return getattr(request.app.state, "leader_lease_manager", None) or get_leader_lease_manager(getattr(request.app.state, "config", None))


def _get_failover_state(request: Request):
    return getattr(request.app.state, "failover_state", None) or get_failover_state()


def _request_base_url(request: Request) -> str:
    try:
        return str(request.base_url).rstrip("/")
    except Exception:
        return ""


async def _peer_cluster_state(request: Request) -> dict:
    bridge = _get_node_bridge(request)
    if bridge is None or not bridge.peer_urls:
        return {
            "peer_count": 0,
            "reachable_peers": 0,
            "unreachable_peers": 0,
            "states": [],
            "errors": [],
        }
    peer_result = await bridge.request_peer_states()
    states = [state for state in peer_result.get("states", []) if isinstance(state, dict)]
    errors = [error for error in peer_result.get("errors", []) if isinstance(error, dict)]
    return {
        "peer_count": len(bridge.peer_urls),
        "reachable_peers": len(states),
        "unreachable_peers": len(errors),
        "states": states,
        "errors": errors,
    }


def _runtime_mode(snapshot: dict, cluster: dict, queue_size: int, failover: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    role = str(snapshot.get("role", "secondary"))
    healthy = snapshot.get("healthy") is True
    has_recent_primary = snapshot.get("has_recent_primary") is True
    memory_is_fresh = snapshot.get("memory_is_fresh") is True
    peer_count = int(cluster.get("peer_count", 0) or 0)
    reachable_peers = int(cluster.get("reachable_peers", 0) or 0)

    if not healthy:
        reasons.append("local_heartbeat_stale")
    if not memory_is_fresh:
        reasons.append("memory_not_fresh")
    if queue_size > 0:
        reasons.append("memory_queue_pending")
    if peer_count > 0 and reachable_peers == 0:
        reasons.append("configured_peers_unreachable")
    if failover.get("should_promote") is True:
        reasons.append("failover_should_promote")
    if role == "secondary" and not has_recent_primary:
        reasons.append("primary_not_recent")

    fallback_reasons = {"failover_should_promote", "primary_not_recent"}
    if any(reason in fallback_reasons for reason in reasons):
        return "fallback", reasons
    if reasons:
        return "degraded", reasons
    return "normal", ["healthy"]


def _memory_write_mode(snapshot: dict, mode: str) -> dict:
    role = str(snapshot.get("role", "secondary"))
    has_recent_primary = snapshot.get("has_recent_primary") is True
    if role == "primary":
        return {"can_write": True, "mode": "local_primary", "target": "local"}
    if has_recent_primary:
        return {"can_write": False, "mode": "delegate_to_primary", "target": "peer_primary"}
    if mode == "fallback":
        return {"can_write": False, "mode": "queue_until_primary", "target": "local_queue"}
    return {"can_write": False, "mode": "read_only_secondary", "target": "none"}


class NodeHeartbeatPayload(BaseModel):
    node_id: str = Field(default="")
    role: str = Field(default="secondary")
    base_url: str = Field(default="")
    metadata: dict = Field(default_factory=dict)


class NodeRolePayload(BaseModel):
    role: str = Field(default="secondary")


class NodeEventPayload(BaseModel):
    type: str = Field(default="unknown")
    data: dict | list | str | int | float | bool | None = None
    source: dict = Field(default_factory=dict)


class NodeMemoryWritePayload(BaseModel):
    key: str = Field(default="")
    value: str = Field(default="")
    source: dict = Field(default_factory=dict)


@router.get("/sessions")
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


@router.post("/heartbeat")
async def node_heartbeat(payload: NodeHeartbeatPayload, request: Request) -> JSONResponse:
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


@router.post("/promote")
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


@router.post("/demote")
async def node_demote(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    lease_manager = _get_leader_lease_manager(request)
    lease_manager.release(coordinator.node_id)
    snapshot = await coordinator.demote()
    await _get_event_bus(request).publish("leader_changed", {"role": "secondary", "state": snapshot})
    log_event("INFO", "node", "demote", detail="node demoted to secondary")
    return JSONResponse({"ok": True, "state": snapshot})


@router.post("/event")
async def node_event(payload: NodeEventPayload, request: Request) -> JSONResponse:
    await relay_memory_event(request, payload.type, {"data": payload.data, "source": payload.source})
    return JSONResponse({"ok": True, "type": payload.type})


@router.post("/memory/request")
async def memory_request(payload: NodeMemoryWritePayload, request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    if not await coordinator.is_primary():
        queue = _get_memory_queue(request)
        queued = queue.enqueue(payload.key, payload.value, source_node=str(payload.source.get("node_id", "")), reason="primary_unavailable")
        await _get_event_bus(request).publish(
            "memory_write_queued",
            {"key": payload.key, "source": payload.source, "state": queue.snapshot()},
        )
        return JSONResponse({"ok": True, "granted": False, "queued": True, "request": queued.to_dict()})

    result = await _get_save_memory_run(request)(
        key=payload.key,
        value=payload.value,
        _repos=getattr(request.app.state, "repos", None),
        _force_local_write=True,
    )
    if result.startswith("[OK]"):
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
    return JSONResponse({"ok": True, "granted": True, "queued": False, "status": "completed", "result": result})


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


@router.get("/failover/status")
async def failover_status(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    state = _get_failover_state(request)
    snapshot = state.snapshot()
    snapshot["ok"] = True
    snapshot["node"] = coordinator.snapshot()
    return JSONResponse(snapshot)
