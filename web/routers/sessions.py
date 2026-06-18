import logging

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from src.api.repos import get_repos
from src.gateway_log import log_event

logger = logging.getLogger(__name__)

router = APIRouter()


def _request_repos(request: Request):
    app = getattr(request, "app", None)
    state = getattr(app, "__dict__", {}).get("state") if app is not None else None
    repos = getattr(state, "repos", None) if state is not None else None
    return repos or get_repos()


@router.post("/sessions/{session_id}/rename")
async def rename(session_id: str, request: Request, name: str = Body(..., embed=True)) -> JSONResponse:
    repos = _request_repos(request)
    new_name = name.strip() or session_id[:8]
    await repos.sessions.require_session(session_id)
    await repos.sessions.rename(session_id, new_name)
    log_event("INFO", "web", "session_renamed", f"{session_id} -> {new_name}", meta={"session_id": session_id, "name": new_name})
    return JSONResponse({"status": "ok"})


@router.post("/sessions/create")
async def create_session(request: Request) -> JSONResponse:
    """Create a new session and return its id."""
    repos = _request_repos(request)
    from src.api import generate_session_id
    from src.api.session import ensure_session
    sid = generate_session_id()
    await ensure_session(sid, session_repo=repos.sessions)
    log_event("INFO", "web", "session_created", sid, meta={"session_id": sid})
    return JSONResponse({"id": sid})


@router.get("/sessions")
async def list_sessions(request: Request) -> JSONResponse:
    """JSON endpoint for sessions list (used by TS prototype)."""
    repos = _request_repos(request)
    raw = await repos.sessions.get_all(50)
    sessions = []
    for s in raw:
        sid, first, last, count, name = s[0], s[1], s[2], s[3], s[4]
        is_favorite = bool(s[6]) if len(s) > 6 else False
        sessions.append({
            "id": sid,
            "name": name or sid[:8],
            "count": count,
            "last_str": str(last)[:10] if last else "",
            "is_favorite": is_favorite,
        })
    return JSONResponse(sessions)


@router.post("/sessions/{session_id}/favorite")
async def toggle_favorite(session_id: str, request: Request, body: dict = Body(...)) -> JSONResponse:
    repos = _request_repos(request)
    favorite = body.get("favorite", False)
    await repos.sessions.set_favorite(session_id, favorite)
    return JSONResponse({"status": "ok"})


@router.post("/sessions/{session_id}/delete")
async def delete(session_id: str, request: Request) -> JSONResponse:
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
