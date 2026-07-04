import logging
import inspect

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from src.gateway_log import log_event
from src.coordination.lan_bridge import NodeLanBridge
from web.routers._node_helpers import _request_base_url, _request_repos
from web.routers._request_repos import is_unconfigured_mock
from web.services.session_directory import merge_session_entries, session_summary_from_row

logger = logging.getLogger(__name__)

router = APIRouter()


def _request_coordinator(request: Request | None):
    if request is None:
        return None
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    return getattr(state, "node_coordinator", None) if state is not None else None


def _request_bridge(request: Request | None):
    if request is None:
        return None
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    bridge = getattr(state, "node_bridge", None) if state is not None else None
    if bridge is not None and not is_unconfigured_mock(bridge):
        return bridge
    coordinator = _request_coordinator(request)
    config = getattr(state, "config", None) if state is not None else None
    if coordinator is None or is_unconfigured_mock(coordinator):
        return None
    bridge = NodeLanBridge(config=config, coordinator=coordinator)
    if state is not None:
        state.node_bridge = bridge
    return bridge


async def _local_session_entries(request: Request | None, limit: int) -> list[dict]:
    repos = _request_repos(request)
    coordinator = _request_coordinator(request)
    snapshot = coordinator.snapshot() if coordinator is not None else {
        "node_id": "",
        "role": "secondary",
        "cluster_name": "kairos",
    }
    raw = await repos.sessions.get_all(limit)
    entries = [
        session_summary_from_row(
            row,
            node_id=snapshot.get("node_id", ""),
            node_role=snapshot.get("role", "secondary"),
            cluster_name=snapshot.get("cluster_name", "kairos"),
            node_platform=snapshot.get("node_platform", ""),
            source_url=_request_base_url(request),
            source_mode="local",
        )
        for row in raw
    ]
    return entries


async def _federated_session_entries(request: Request | None, limit: int) -> list[dict]:
    local = await _local_session_entries(request, limit)
    bridge = _request_bridge(request)
    if bridge is None or not bridge.peer_urls:
        return local
    if not inspect.iscoroutinefunction(getattr(bridge, "request_session_directory", None)):
        return local
    remote_payload = await bridge.request_session_directory(limit=limit)
    remote_sessions = remote_payload.get("sessions", []) if isinstance(remote_payload, dict) else []
    merged = merge_session_entries(local, [s for s in remote_sessions if isinstance(s, dict)])
    return merged


@router.post("/sessions/{session_id}/rename")
async def rename(session_id: str, request: Request = None, name: str = Body(..., embed=True)) -> JSONResponse:
    repos = _request_repos(request)
    new_name = name.strip() or session_id[:8]
    await repos.sessions.require_session(session_id)
    await repos.sessions.rename(session_id, new_name)
    log_event("INFO", "web", "session_renamed", f"{session_id} -> {new_name}", meta={"session_id": session_id, "name": new_name})
    return JSONResponse({"status": "ok"})


@router.post("/sessions/create")
async def create_session(*, request: Request = None) -> JSONResponse:
    """Create a new session and return its id."""
    repos = _request_repos(request)
    from src.api.orchestrator import generate_session_id
    from src.api.session import ensure_session
    sid = generate_session_id()
    await ensure_session(sid, session_repo=repos.sessions)
    log_event("INFO", "web", "session_created", sid, meta={"session_id": sid})
    return JSONResponse({"id": sid})


@router.get("/sessions")
async def list_sessions(limit: int = 50, *, request: Request = None) -> JSONResponse:
    """JSON endpoint for sessions list (used by TS prototype)."""
    sessions = await _federated_session_entries(request, limit)
    return JSONResponse(sessions)


@router.post("/sessions/{session_id}/favorite")
async def toggle_favorite(session_id: str, body: dict = Body(...), *, request: Request = None) -> JSONResponse:
    repos = _request_repos(request)
    favorite = body.get("favorite", False)
    await repos.sessions.set_favorite(session_id, favorite)
    return JSONResponse({"status": "ok"})


@router.post("/sessions/{session_id}/delete")
async def delete(session_id: str, request: Request = None) -> JSONResponse:
    repos = _request_repos(request)
    await repos.sessions.delete_cascade(session_id, repos=repos)
    log_event("INFO", "web", "session_deleted", session_id, meta={"session_id": session_id})
    # Notify other web UI tabs via SSE
    try:
        from web.services.event_bus import get_event_bus, IEventBus
        bus: IEventBus = getattr(request.app.state, 'event_bus', None) or get_event_bus()
        await bus.publish("session_deleted", {"session_id": session_id})
    except Exception:
        logger.warning("Failed to publish session_deleted event for %s", session_id, exc_info=True)
    return JSONResponse({"status": "ok"})
