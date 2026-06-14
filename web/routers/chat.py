import logging
import os
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, UploadFile, File as FastAPIFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.core.orchestrator import chat_stream as core_chat_stream
from src.llm.client import chat_stream as llm_chat_stream
from src.core.orchestrator_contract import OrchestratorDeps
from src.core.history_rebuilder import rebuild_history
from src.core.history_contract import HistoryRebuildDeps
from src.llm.selector import get_default_model
from src.api.messages import save_message_record as db_save_message
from src.api.session import ensure_session
from src.core.debug_info import DebugInfo
from src.memory.repos import get_repos
from src.memory.repos import MessageRecord
from web.services.chat_stream import build_stream_generator
from web.services.chat_stream_contract import StreamGeneratorDeps
from web.services.stream_retry_handler import StreamRetryHandler

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB per file


class ChatPayload(BaseModel):
    message: str
    model: str | None = None
    tagged: bool = False


def _save_attachments(session_id: str, files: list[UploadFile]) -> list[dict]:
    if not files or not isinstance(files, list):
        return []
    attachments_dir = os.path.join("memory", "attachments", session_id)
    os.makedirs(attachments_dir, exist_ok=True)
    saved = []
    for f in files:
        content = f.file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            logger.warning("File %s exceeds size limit, skipping", f.filename)
            continue
        ext = os.path.splitext(f.filename or "file")[1]
        safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
        path = os.path.join(attachments_dir, safe_name)
        with open(path, "wb") as out:
            out.write(content)
        saved.append({
            "original_name": f.filename or "file",
            "saved_name": safe_name,
            "size": len(content),
            "content_type": f.content_type or "application/octet-stream",
        })
    return saved


def _build_message_with_attachments(message: str, attachments: list[dict]) -> str:
    if not attachments:
        return message
    lines = [message, ""]
    for a in attachments:
        lines.append(f"[Archivo: {a['original_name']}]")
    return "\n".join(lines)


@router.post("/chat/{session_id}")
async def chat(
    session_id: str,
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    model: str | None = Query(None),
    files: list[UploadFile] = FastAPIFile(default=[]),
) -> Response:
    if not session_id or not session_id.strip():
        raise HTTPException(400, "Invalid session_id")
    if not message.strip():
        raise HTTPException(400, detail="Empty message")
    model = model or get_default_model()

    attachments = _save_attachments(session_id, files)
    full_message = _build_message_with_attachments(message, attachments)

    await ensure_session(session_id)
    repos = get_repos()
    try:
        history = await rebuild_history(session_id, model, messages_repo=repos.messages)
    except Exception as e:
        logger.error("Error rebuilding history for %s: %s", session_id, e)
        raise HTTPException(500, "Error loading history")

    try:
        await db_save_message(MessageRecord(session_id=session_id, role="user", content=full_message, model=model), repos=repos)
    except Exception as e:
        logger.error("Error saving user message for %s: %s", session_id, e)

    _journal_start = time.time()
    _journal_user_msg = full_message

    from web.services.message_persister import save_assistant_message

    async def _wrapped_chat_stream(*a, **kw):
        async for event in core_chat_stream(*a, **kw, deps=OrchestratorDeps(repos=repos)):
            yield event

    async def _wrapped_save(*a, **kw):
        result = await save_assistant_message(*a, **kw, repos=repos)
        try:
            from src.chat_journal import log_turn
            duration_ms = int((time.time() - _journal_start) * 1000)
            log_turn(
                session_id=session_id,
                user_msg=_journal_user_msg,
                assistant_msg=kw.get("full_content", "")[:200] if "full_content" in kw else "",
                tools_used=[],
                model=model,
                duration_ms=duration_ms,
                token_count=kw.get("debug_info", DebugInfo()).total_tokens if "debug_info" in kw else 0,
            )
        except Exception:
            pass
        return result

    generate = build_stream_generator(
        session_id,
        full_message,
        history,
        model,
        background_tasks,
        deps=StreamGeneratorDeps(
            chat_stream_fn=_wrapped_chat_stream,
            retry_handler=StreamRetryHandler(max_retries=2, llm_chat_stream_fn=llm_chat_stream),
            save_fn=_wrapped_save,
        ),
    )
    return StreamingResponse(generate(), media_type="application/x-ndjson")

