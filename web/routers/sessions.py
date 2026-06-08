from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from src.memory import rename_session, delete_session

router = APIRouter()


@router.post("/sessions/{session_id}/rename")
async def rename(session_id: str, name: str = Form(...)):
    rename_session(session_id, name.strip() or session_id[:8])
    return HTMLResponse("OK")


@router.post("/sessions/{session_id}/delete")
async def delete(session_id: str):
    delete_session(session_id)
    return HTMLResponse("OK")
