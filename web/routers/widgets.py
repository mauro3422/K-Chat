from fastapi import APIRouter

from src.memory import save_widget_state

router = APIRouter()


@router.post("/sessions/{session_id}/widgets/{widget_id}/state")
async def set_widget_state(session_id: str, widget_id: str, payload: dict):
    state = payload.get("state", "{}")
    save_widget_state(session_id, widget_id, state)
    return {"status": "ok"}
