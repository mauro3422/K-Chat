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
from src.memory.types import DebugInfo
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
        # Marker includes both original name and saved name for frontend rendering
        lines.append(f"[Archivo: {a['original_name']}|{a['saved_name']}]")
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

    repos = get_repos()
    await repos.sessions.ensure(session_id)
    try:
        history = await rebuild_history(session_id, model, messages_repo=repos.messages)
    except Exception as e:
        logger.error("Error rebuilding history for %s: %s", session_id, e)
        raise HTTPException(500, "Error loading history")

    try:
        await repos.messages.save_record(MessageRecord(session_id=session_id, role="user", content=full_message, model=model))
    except Exception as e:
        logger.error("Error saving user message for %s: %s", session_id, e)

    _journal_start = time.time()
    _journal_user_msg = full_message

    from web.services.message_persister import save_assistant_message

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
            retry_handler=StreamRetryHandler(max_retries=2, llm_chat_stream_fn=llm_chat_stream),
            save_fn=_wrapped_save,
        ),
    )
    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/chat/{session_id}/attachment/{filename}")
async def get_attachment(session_id: str, filename: str):
    """Serve an attachment file (images, PDFs, etc.) from the session's attachments dir."""
    import re
    if not re.match(r'^[\w\-\.]+$', filename):
        raise HTTPException(400, "Invalid filename")
    safe_dir = os.path.join("memory", "attachments", session_id)
    file_path = os.path.join(safe_dir, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404, "Attachment not found")

    ext = os.path.splitext(filename)[1].lower()
    content_types = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
        ".pdf": "application/pdf",
        ".mp3": "audio/mpeg", ".wav": "audio/wav",
    }
    ct = content_types.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        content = f.read()

    return Response(content=content, media_type=ct)
