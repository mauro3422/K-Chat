from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from src.memory.repos import get_repos

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
    await repos.sessions.require_session(session_id)
    await repos.sessions.delete_cascade(session_id, repos=repos)
    return JSONResponse({"status": "ok"})
