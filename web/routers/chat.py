import logging
import os
import uuid
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, UploadFile, File as FastAPIFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.background import auto_rename_session
from src.api.llm_client import get_default_model, llm_chat_stream
from src.api.orchestrator import OrchestratorDeps, rebuild_history
from src.api.repos import MessageRecord, get_repos
from web.services.chat_stream import build_stream_generator
from web.services.chat_stream_contract import StreamGeneratorDeps
from web.services.protocols import MessagePersisterProtocol, StreamGeneratorProtocol
from web.services.session_stream_locks import SessionStreamLockManager
from web.services.stream_retry_handler import (
    StreamRetryHandler,
    build_continuation_instruction,
)
from web.services.stream_contract import serialize_stream_event

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB per file


def _resolve_origin_node_id() -> str:
    """Return the active coordinator's node_id, or '' when unconfigured.

    Stamps new sessions with ``origin_node_id`` so the federated
    session directory knows where the session was born.
    """
    try:
        from src.coordination.node_state import peek_node_coordinator
        coordinator = peek_node_coordinator()
        if coordinator is None:
            return ""
        return getattr(coordinator, "node_id", "") or ""
    except Exception:
        return ""


def _get_stream_lock_manager(request: Request) -> SessionStreamLockManager:
    state = request.app.state
    state_dict = getattr(state, "__dict__", {})
    manager = state_dict.get("chat_stream_lock_manager")
    if isinstance(manager, SessionStreamLockManager):
        return manager

    manager = SessionStreamLockManager()
    setattr(state, "chat_stream_lock_manager", manager)
    return manager


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
    request: Request,
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    resume: bool = Form(False),
    retry_error_type: str = Form(""),
    retry_error_message: str = Form(""),
    retry_count: int = Form(0),
    model: str | None = Query(None),
    files: list[UploadFile] = FastAPIFile(default=[]),
) -> Response:
    if not session_id or not session_id.strip():
        raise HTTPException(400, "Invalid session_id")
    if not message.strip():
        raise HTTPException(400, detail="Empty message")

    lock_manager = _get_stream_lock_manager(request)
    session_lock = await lock_manager.try_acquire(session_id)
    if session_lock is None:
        async def _busy_stream():
            yield serialize_stream_event(
                "error",
                {
                    "type": "bad_request",
                    "message": "Ya hay un stream activo para esta sesión",
                },
            )

        return StreamingResponse(_busy_stream(), media_type="application/x-ndjson")

    try:
        model = model or get_default_model()

        attachments = _save_attachments(session_id, files)
        full_message = _build_message_with_attachments(message, attachments)

        repos = getattr(request.app.state, 'repos', None) or get_repos()
        orchestrator_deps = OrchestratorDeps(
            repos=repos,
            history_service=request.app.state.history_service,
            telemetry_service=request.app.state.telemetry_service,
            llm_service=request.app.state.llm_service,
            tool_service=request.app.state.tool_service,
            retrieval_service=request.app.state.retrieval_service,
            session_id=session_id,
            tagged=True,
            background_tasks=background_tasks,
        )
        await repos.sessions.ensure(
            session_id,
            origin_node_id=_resolve_origin_node_id(),
        )
        checkpoint = None
        checkpoint_repo = getattr(repos, "stream_checkpoints", None)
        if resume is True and checkpoint_repo is not None:
            checkpoint = await checkpoint_repo.get(session_id)

        try:
            if checkpoint:
                history = json.loads(checkpoint.get("history_json") or "[]")
            else:
                history = await rebuild_history(
                    session_id,
                    model,
                    messages_repo=repos.messages,
                )
        except Exception as e:
            logger.error("Error rebuilding history for %s: %s", session_id, e)
            raise HTTPException(500, "Error loading history")

        original_message = full_message
        stream_message = full_message
        initial_phases: list[dict[str, Any]] = []
        if checkpoint:
            original_message = checkpoint.get("original_message") or full_message
            partial_content = checkpoint.get("partial_content") or ""
            partial_reasoning = checkpoint.get("partial_reasoning") or ""
            if partial_content or partial_reasoning:
                partial = {
                    "role": "assistant",
                    "content": partial_content or None,
                }
                if partial_reasoning:
                    partial["reasoning_content"] = partial_reasoning
                history.append(partial)
            retry_error_type = (
                retry_error_type
                or checkpoint.get("error_type")
                or "unknown"
            )
            retry_error_message = (
                retry_error_message
                or checkpoint.get("error_message")
                or ""
            )
            retry_count = max(
                retry_count,
                int(checkpoint.get("retry_count") or 0) + 1,
            )
            stream_message = build_continuation_instruction(
                retry_error_type,
                retry_error_message,
            )
            orchestrator_deps.is_continuation = True
            initial_phases = json.loads(checkpoint.get("phases_json") or "[]")
        else:
            try:
                await repos.messages.save_record(
                    MessageRecord(
                        session_id=session_id,
                        role="user",
                        content=full_message,
                        model=model,
                    )
                )
            except Exception as e:
                logger.error("Error saving user message for %s: %s", session_id, e)

        from web.services.message_persister import save_assistant_message

        async def _wrapped_save(*a: Any, **kw: Any) -> None:
            logbus = getattr(request.app.state, "logbus", None)
            user_msg = kw.pop("user_msg", full_message)
            return await save_assistant_message(*a, **kw, user_msg=user_msg, repos=repos, logbus=logbus)

        async def _rename_and_publish(sid: str, first_message: str, selected_model: str) -> None:
            title = await auto_rename_session(
                sid,
                first_message,
                selected_model,
                session_repo=repos.sessions,
            )
            if title:
                await request.app.state.event_bus.publish(
                    "session_renamed",
                    {"session_id": sid, "name": title},
                )

        generate = build_stream_generator(
            session_id,
            stream_message,
            history,
            model,
            background_tasks,
            deps=StreamGeneratorDeps(
                retry_handler=StreamRetryHandler(max_retries=2, llm_chat_stream_fn=llm_chat_stream),
                save_fn=_wrapped_save,
                rename_fn=_rename_and_publish,
                session_artifact_coordinator=request.app.state.session_artifact_coordinator,
                original_message=original_message,
                retry_error_type=retry_error_type,
                retry_error_message=retry_error_message,
                retry_count=retry_count,
                initial_phases=initial_phases,
            ),
            orchestrator_deps=orchestrator_deps,
        )
    except Exception:
        lock_manager.release(session_id, session_lock)
        raise

    async def _guarded_stream():
        try:
            async for chunk in generate():
                yield chunk
        finally:
            lock_manager.release(session_id, session_lock)

    return StreamingResponse(_guarded_stream(), media_type="application/x-ndjson")


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


@router.delete("/chat/{session_id}/messages/{message_id}")
async def delete_message(session_id: str, request: Request, message_id: int) -> Response:
    repos = getattr(request.app.state, 'repos', None) or get_repos()
    success = await repos.messages.delete_message(message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found or already deleted")

    try:
        from web.services.event_bus import get_event_bus, IEventBus
        bus: IEventBus = getattr(request.app.state, 'event_bus', None) or get_event_bus()
        await bus.publish("message_deleted", {"session_id": session_id, "message_id": message_id})
    except Exception as e:
        logger.warning("Failed to publish message_deleted event: %s", e)

    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "ok"})
