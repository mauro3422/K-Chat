import logging

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.api import get_repos

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sessions/{session_id}/rename")
async def rename(session_id: str, name: str = Body(..., embed=True)) -> JSONResponse:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    await repos.sessions.rename(session_id, name.strip() or session_id[:8])
    return JSONResponse({"status": "ok"})


@router.post("/sessions/{session_id}/delete")
async def delete(session_id: str) -> JSONResponse:
    repos = get_repos()
    # No require_session — delete_cascade is idempotent and handles missing rows
    await repos.sessions.delete_cascade(session_id, repos=repos)
    # Notify other web UI tabs via SSE
    try:
        from web.services.event_bus import get_event_bus
        bus = get_event_bus()
        await bus.publish("session_deleted", {"session_id": session_id})
    except Exception:
        logger.warning("Failed to publish session_deleted event for %s", session_id, exc_info=True)
    return JSONResponse({"status": "ok"})
