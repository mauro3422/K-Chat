import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.chat import get_default_model
from src.api.history import rebuild_history
from src.api.messages import save_message as db_save_message
from src.api.session import ensure_session
from web.services.chat_stream import build_stream_generator

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatPayload(BaseModel):
    message: str
    model: str | None = None
    tagged: bool = False


@router.post("/chat/{session_id}")
def chat(session_id: str, background_tasks: BackgroundTasks, payload: ChatPayload) -> Response:
    if not session_id or not session_id.strip():
        raise HTTPException(400, "Invalid session_id")
    if not payload.message.strip():
        return ""
    model = payload.model or get_default_model()

    ensure_session(session_id)
    try:
        history = rebuild_history(session_id, model)
    except Exception as e:
        logger.error("Error rebuilding history for %s: %s", session_id, e)
        raise HTTPException(500, "Error loading history")

    try:
        db_save_message(session_id, "user", payload.message, model)
    except Exception as e:
        logger.error("Error saving user message for %s: %s", session_id, e)

    generate = build_stream_generator(session_id, payload.message, history, model, background_tasks)
    return StreamingResponse(generate(), media_type="application/x-ndjson")
