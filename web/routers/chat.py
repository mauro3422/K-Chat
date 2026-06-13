import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.llm.policy import get_default_model
from src.core.orchestrator import chat_stream as core_chat_stream
from src.api.history import rebuild_history
from src.api.messages import save_message as db_save_message
from src.api.session import ensure_session
from src.memory.repos import get_repos
from web.services.chat_stream import build_stream_generator
from web.services.stream_retry_handler import StreamRetryHandler

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatPayload(BaseModel):
    message: str
    model: str | None = None
    tagged: bool = False


@router.post("/chat/{session_id}")
def chat(
    session_id: str,
    background_tasks: BackgroundTasks,
    payload: ChatPayload,
    model: str | None = None,
) -> Response:
    if not session_id or not session_id.strip():
        raise HTTPException(400, "Invalid session_id")
    if not payload.message.strip():
        return ""
    model = payload.model or model or get_default_model()

    ensure_session(session_id)
    repos = get_repos()
    try:
        history = rebuild_history(session_id, model, repos.messages)
    except Exception as e:
        logger.error("Error rebuilding history for %s: %s", session_id, e)
        raise HTTPException(500, "Error loading history")

    try:
        db_save_message(session_id, "user", payload.message, model)
    except Exception as e:
        logger.error("Error saving user message for %s: %s", session_id, e)

    generate = build_stream_generator(
        session_id,
        payload.message,
        history,
        model,
        background_tasks,
        chat_stream_fn=lambda *a, **kw: core_chat_stream(*a, **kw, repos=repos),
        retry_handler=StreamRetryHandler(max_retries=2),
    )
    return StreamingResponse(generate(), media_type="application/x-ndjson")
