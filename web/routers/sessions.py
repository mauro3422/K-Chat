from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.api.session import rename_session, delete_session, _require_session
from src.memory.repos import get_repos

router = APIRouter()


@router.post("/sessions/{session_id}/rename")
async def rename(session_id: str, name: str = Body(..., embed=True)) -> JSONResponse:
    await _require_session(session_id)
    await rename_session(session_id, name.strip() or session_id[:8])
    return JSONResponse({"status": "ok"})


@router.post("/sessions/{session_id}/delete")
async def delete(session_id: str) -> JSONResponse:
    await _require_session(session_id)
    await delete_session(session_id, repos=get_repos())
    return JSONResponse({"status": "ok"})
