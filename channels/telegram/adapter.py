"""Adapter — bridges Telegram messages to the K-Chat core pipeline.

Processes messages through ``src.core.orchestrator.chat_stream()`` and
yields tagged strings for the Telegram renderer.

Tags follow the convention::

    ``__reasoning__:<text>``  — reasoning (thinking) tokens
    ``__content__:<text>``    — visible content tokens
    ``__tool__:<name>``       — tool call
    ``__error__:<message>``   — error

Telegram sessions are persistent across bot restarts via the session_id
mapping in the K-Chat memory DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from channels.telegram.config import TelegramConfig
from channels.telegram.ws_client import get_ws_client

logger = logging.getLogger(__name__)

# ─── SSE notify URL ───────────────────────────────────────────────────
_SSE_NOTIFY_URL: str | None = None

def _get_sse_notify_url() -> str:
    """Get the SSE notify URL, configurable via env KAIROS_WEB_URL."""
    global _SSE_NOTIFY_URL
    if _SSE_NOTIFY_URL is None:
        base = os.environ.get("KAIROS_WEB_URL", "http://127.0.0.1:8000")
        _SSE_NOTIFY_URL = base.rstrip("/") + "/api/events/notify"
    return _SSE_NOTIFY_URL


# ─── Channel marker ────────────────────────────────────────────────────
CHANNEL_SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "Mensajes del usuario llegan desde Telegram. Respondé sin mencionar "
        "el canal ni usar emojis de Telegram. Markdown funciona. "
        "No digas 'estás en Telegram' ni 'conectado desde'."
    ),
}

# ─── Timeout ───────────────────────────────────────────────────────────
_STREAM_TIMEOUT = 120  # seconds


# ─── Public API ────────────────────────────────────────────────────────

async def process_message(
    text: str,
    chat_id: int,
    config: TelegramConfig,
) -> AsyncGenerator[str, None]:
    """Process a Telegram message through the K-Chat core pipeline.

    Yields tagged strings for the renderer to display.

    Args:
        text: The message text from the user.
        chat_id: Telegram chat ID for session persistence.
        config: Telegram configuration.

    Yields:
        Tagged strings: ``__reasoning__:...``, ``__content__:...``,
        ``__tool__:...``, ``__error__:...``.
    """
    _late_imports = _LazyImports()

    session_id, history = await _get_or_create_session(
        chat_id, _late_imports,
    )
    model = _late_imports.get_default_model()

    # ── Commands (tagged as __content__ so the renderer sends them) ──────
    if text == "/start":
        yield (
            "__content__:"
            "¡Hola! Soy **Kairos**, tu asistente personal.\n\n"
            "Comandos:\n"
            "/new — Nueva sesión\n"
            "/reset — Reiniciar\n"
            "/help — Ayuda\n\n"
            "Mandame lo que necesites."
        )
        return

    if text == "/help":
        yield (
            "__content__:"
            "**Comandos:**\n"
            "/new — Nueva sesión\n"
            "/reset — Reiniciar\n"
            "/help — Ayuda\n\n"
            "Tengo herramientas, memoria, búsqueda web y más."
        )
        return

    if text == "/reset":
        # Keep same session, delete all messages in it (conversation reset)
        repos = _late_imports.get_repos()
        await repos.messages.delete_session_messages(session_id)
        yield "__content__:✅ Chat reiniciado."
        return

    if text == "/new":
        # Archive old session, create brand new one
        await _reset_session(chat_id, _late_imports)
        yield "__content__:✅ Nueva sesión creada."
        return

    if text == "/delete":
        # Delete current session (cascade: messages + session)
        repos = _late_imports.get_repos()
        await repos.sessions.delete_cascade(session_id, repos)
        # Also clear persisted telegram msg IDs for this chat
        try:
            from src.memory.repos.telegram_msg_id_repository import TelegramMsgIdRepo
            repo = TelegramMsgIdRepo()
            await repo.delete_chat(chat_id)
        except Exception:
            pass
        # Notify web UI so sidebar refreshes
        try:
            import httpx
            async with httpx.AsyncClient() as sse_client:
                await sse_client.post(
                    _get_sse_notify_url(),
                    json={"type": "session_deleted", "data": {"session_id": session_id}},
                    timeout=3,
                )
        except Exception:
            logger.debug("SSE notify failed (delete session): %s", _get_sse_notify_url())
        yield "__content__:🗑 Sesión eliminada."
        return

    # ── /sessions — list or switch ────────────────────────────────────
    if text.lower().startswith("/sessions"):
        result = await _handle_sessions_command(text, chat_id, _late_imports)
        for line in result:
            yield f"__content__:{line}"
        return

    if text.startswith("__voice__:"):
        yield "__content__:🎤 Mensaje de voz recibido. Transcripción próximamente."
        return

    # ── Save user message ───────────────────────────────────────────────
    repos = _late_imports.get_repos()
    await repos.messages.save_record(_late_imports.MessageRecord(
        session_id=session_id,
        role="user",
        content=text,
        model=model,
        reasoning="",
        phases="[]",
    ))
    # Notify web UI via SSE so user message appears in real-time
    try:
        import httpx
        async with httpx.AsyncClient() as sse_client:
            await sse_client.post(
                _get_sse_notify_url(),
                json={
                    "type": "new_message",
                    "data": {
                        "session_id": session_id,
                        "role": "user",
                        "content": text,
                        "ts": int(time.time()),
                    },
                },
                timeout=3,
            )
    except Exception:
        logger.warning("SSE notify failed (user msg): %s", _get_sse_notify_url())

    # ── Stream processing ───────────────────────────────────────────────
    logger.info("TG[%d] processing: %.60s", chat_id, text)

    try:
        reasoning_buf: list[str] = []    # flush buffer (20-token chunks)
        full_reasoning: list[str] = []   # accumulates ALL reasoning for DB
        content_buf: list[str] = []
        phases_output: list[dict] = []   # accumulates phases for web UI
        reasoning_ws_interval = 5        # WS/SSE flush (smooth web UI)
        reasoning_tg_interval = 20       # Telegram API flush (fewer edits = less lag)
        content_ws_interval = 5
        content_tg_interval = 15
        start_time = time.time()

        async for event_type, token in _late_imports.chat_stream(
            message_user=text,
            history=history,
            model=model,
            session_id=session_id,
            tagged=True,
            phases_output=phases_output,
        ):
            # ── Timeout check ─────────────────────────────────────────
            if time.time() - start_time > _STREAM_TIMEOUT:
                if content_buf:
                    yield f"__content__:{"".join(content_buf)}"
                elif reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                else:
                    yield "__error__:Operación agotada. Mandame el mensaje de nuevo."
                # Save partial data before exiting
                partial = "".join(content_buf or reasoning_buf or full_reasoning).strip()
                if partial:
                    pr = "".join(full_reasoning).strip()
                    pc = "".join(content_buf).strip()
                    try:
                        await _persist_partial_conversation(
                            session_id, text, pc or partial, pr, _late_imports,
                        )
                    except Exception:
                        pass
                return

            # ── Reasoning ──────────────────────────────────────────────
            if event_type == "reasoning":
                reasoning_buf.append(token)
                full_reasoning.append(token)  # keep for DB persistence
                rlen = len(reasoning_buf)
                if rlen == 1:
                    # First token → flush to both
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                    asyncio.create_task(get_ws_client().send_event("stream:reasoning", {
                        "session_id": session_id,
                        "text": "".join(reasoning_buf),
                    }))
                else:
                    # WS flush every reasoning_ws_interval (smooth web UI)
                    if rlen % reasoning_ws_interval == 0:
                        asyncio.create_task(get_ws_client().send_event("stream:reasoning", {
                            "session_id": session_id,
                            "text": "".join(reasoning_buf),
                        }))
                    # Telegram flush every reasoning_tg_interval (fewer edits)
                    if rlen % reasoning_tg_interval == 0:
                        yield f"__reasoning__:{"".join(reasoning_buf)}"

            # ── Content ────────────────────────────────────────────────
            elif event_type == "content":
                # Flush any pending reasoning first
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                    reasoning_buf = []
                content_buf.append(token)
                clen = len(content_buf)
                if clen == 1:
                    # First token → flush to both
                    yield f"__content__:{"".join(content_buf)}"
                    asyncio.create_task(get_ws_client().send_event("stream:content", {
                        "session_id": session_id,
                        "text": "".join(content_buf),
                    }))
                else:
                    # WS flush every content_ws_interval (smooth web UI)
                    if clen % content_ws_interval == 0:
                        asyncio.create_task(get_ws_client().send_event("stream:content", {
                            "session_id": session_id,
                            "text": "".join(content_buf),
                        }))
                    # Telegram flush every content_tg_interval (fewer edits)
                    if clen % content_tg_interval == 0:
                        yield f"__content__:{"".join(content_buf)}"

            # ── Tool call ──────────────────────────────────────────────
            elif event_type == "tool_call":
                try:
                    tc = json.loads(token) if isinstance(token, str) else token
                    name = tc.get("name", tc.get("function", {}).get("name", ""))
                    if name == "_stream_args":
                        continue
                    tool_id = tc.get("id", "")
                    status = tc.get("status", "calling")
                except Exception:
                    name = str(token)[:30]
                    tool_id = ""
                    status = "calling"

                # Notify web UI about tool call in real-time
                asyncio.create_task(get_ws_client().send_event("stream:tool", {
                    "session_id": session_id,
                    "tool_name": name,
                    "tool_id": tool_id,
                    "status": status,
                }))

                # Flush reasoning (shows why the tool was called),
                # discard content (it's always incomplete before a tool)
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                    reasoning_buf = []
                content_buf = []
                yield f"__tool__:{tool_id}:{name}:{status}"

            # ── Error ──────────────────────────────────────────────────
            elif event_type == "error":
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                if content_buf:
                    yield f"__content__:{"".join(content_buf)}"
                # Notify web UI about error
                asyncio.create_task(get_ws_client().send_event("stream:error", {
                    "session_id": session_id,
                    "error": str(token),
                }))
                yield f"__error__:{token}"
                return

            # ── Heartbeat ──────────────────────────────────────────────
            elif event_type == "heartbeat":
                pass

        # ── Final flush + persist ──────────────────────────────────────
        if reasoning_buf:
            yield f"__reasoning__:{"".join(reasoning_buf)}"

        if content_buf:
            final_content = "".join(content_buf).strip()
            final_reasoning = "".join(full_reasoning).strip()
            if final_content:
                yield f"__content__:{final_content}"
                # Final stream flush so web UI has all content before new_message
                if final_reasoning:
                    asyncio.create_task(get_ws_client().send_event("stream:reasoning", {
                        "session_id": session_id,
                        "text": final_reasoning,
                    }))
                if final_content:
                    asyncio.create_task(get_ws_client().send_event("stream:content", {
                        "session_id": session_id,
                        "text": final_content,
                    }))
                phases_json = json.dumps(phases_output) if phases_output else "[]"
                await _persist_conversation(
                    session_id, text, final_content, final_reasoning, phases_json, _late_imports,
                )
                # Auto-rename Telegram session (non-blocking background task)
                try:
                    from src.background_tasks import auto_rename_session
                    asyncio.create_task(auto_rename_session(
                        session_id, text, _late_imports.get_default_model(),
                    ))
                except Exception:
                    pass
                return

        logger.info("TG[%d] no text content generated", chat_id)
        # Save partial data even if no final content was generated
        partial = "".join(content_buf or reasoning_buf or full_reasoning).strip()
        if partial:
            partial_reasoning = "".join(full_reasoning).strip()
            partial_content = "".join(content_buf).strip()
            await _persist_partial_conversation(
                session_id, text, partial_content or partial,
                partial_reasoning, _late_imports,
            )

    except GeneratorExit:
        logger.info("TG[%d] stream interrupted (GeneratorExit)", chat_id)
        # Save partial data before the generator is closed
        try:
            partial = "".join(content_buf or reasoning_buf or full_reasoning).strip() if 'content_buf' in dir() else ""
            if partial:
                pr = "".join(full_reasoning).strip() if 'full_reasoning' in dir() else ""
                pc = "".join(content_buf).strip() if 'content_buf' in dir() else ""
                await _persist_partial_conversation(
                    session_id, text, pc or partial, pr, _late_imports,
                )
        except Exception:
            pass
        return

    except Exception as e:
        logger.exception("TG[%d] processing error", chat_id)
        # Save whatever we have before yielding the error
        partial = "".join(content_buf or reasoning_buf or full_reasoning).strip() if 'content_buf' in dir() else ""
        if partial:
            partial_reasoning = "".join(full_reasoning).strip() if 'full_reasoning' in dir() else ""
            partial_content = "".join(content_buf).strip() if 'content_buf' in dir() else ""
            await _persist_partial_conversation(
                session_id, text, partial_content or partial,
                partial_reasoning, _late_imports,
            )
        yield f"__error__:{e}"


# ─── Session management ────────────────────────────────────────────────

async def _get_or_create_session(
    chat_id: int, li: _LazyImports,
) -> tuple[str, list[dict[str, Any]]]:
    """Get or create a persistent Telegram session.

    Sessions are identified by ``telegram_chat_id`` column, NOT by name.
    This allows auto-rename (LLM-generated title) without breaking lookup.
    """
    repos = li.get_repos()
    session_id = await repos.sessions.find_by_telegram_chat_id(chat_id)
    history: list[dict[str, Any]] = []

    if session_id:
        logger.info("Restored session %s for chat %d", session_id, chat_id)
        await repos.sessions.ensure(session_id)
        try:
            raw = await repos.messages.get_session_messages(session_id)
            for row in raw:
                role = row[0]
                content = row[1]
                tool_calls_raw = row[6] if len(row) > 6 else None
                tool_call_id = row[7] if len(row) > 7 else None
                msg: dict = {"role": role}
                msg["content"] = content or ""
                if role == "tool" and tool_call_id:
                    msg["tool_call_id"] = tool_call_id
                if role == "assistant" and tool_calls_raw:
                    import json
                    try:
                        tc_list = json.loads(tool_calls_raw) if isinstance(tool_calls_raw, str) else tool_calls_raw
                        if tc_list:
                            msg["tool_calls"] = tc_list
                    except (json.JSONDecodeError, TypeError):
                        pass
                history.append(msg)

            # Strip incomplete tool chains
            cleaned: list[dict[str, Any]] = []
            for i, msg in enumerate(history):
                if msg["role"] == "assistant" and msg.get("tool_calls"):
                    needed = len(msg["tool_calls"])
                    following = history[i + 1:i + 1 + needed]
                    tool_ids_avail = [
                        m.get("tool_call_id", "") for m in following
                        if m["role"] == "tool"
                    ]
                    if len(tool_ids_avail) < needed:
                        logger.debug("Drop incomplete tool chain at msg %d", i)
                        continue
                cleaned.append(msg)
            history = cleaned
        except Exception:
            history = []
    else:
        session_id = f"tele_{uuid.uuid4().hex[:20]}"
        logger.info("New Telegram session %s for chat %d", session_id, chat_id)
        await repos.sessions.ensure(session_id)
        await repos.sessions.update_telegram_chat_id(session_id, chat_id)

    model = li.get_default_model()
    system_prompt = li.build_system_prompt(model)
    history = [system_prompt, CHANNEL_SYSTEM_MESSAGE] + history
    return session_id, history


async def _reset_session(chat_id: int, li: _LazyImports) -> str:
    """Create a brand new session for a Telegram chat.

    The old session stays in the DB (with its ``telegram_chat_id``)
    so ``/sessions`` can still list it.
    """
    repos = li.get_repos()
    session_id = f"tele_{uuid.uuid4().hex[:20]}"
    await repos.sessions.ensure(session_id)
    await repos.sessions.update_telegram_chat_id(session_id, chat_id)
    logger.info("New Telegram session %s for chat %d", session_id, chat_id)
    return session_id


# ─── /sessions command ──────────────────────────────────────────────────

async def _handle_sessions_command(
    text: str, chat_id: int, li: _LazyImports,
) -> list[str]:
    """Handle ``/sessions`` (list) and ``/sessions <n>`` (switch).

    Sessions are identified by ``telegram_chat_id`` column, newest first.
    Returns a list of content lines to yield as ``__content__:``.
    """
    repos = li.get_repos()
    tg_sessions = await repos.sessions.find_all_by_telegram_chat_id(chat_id)

    if not tg_sessions:
        return ["No hay sesiones de Telegram."]

    # If no number argument, list sessions
    parts = text.strip().split(None, 1)
    if len(parts) == 1:
        lines = ["📋 **Tus sesiones de Telegram:**"]
        for i, (sid, name, created_at) in enumerate(tg_sessions, 1):
            label = name if name else sid[:12]
            last_date = created_at[:10] if created_at else "?"
            active = "📌 " if i == 1 else ""
            lines.append(f"  `{i}`. {active}{label} — {last_date}")
            if active:
                lines.append(f"     🆔 `{sid[:12]}...`")
        lines.append("")
        lines.append("Usá `/sessions <n>` para cambiar a una sesión.")
        return lines

    # /sessions <n> — switch to session by index (1-based)
    try:
        idx = int(parts[1]) - 1
        if idx < 0 or idx >= len(tg_sessions):
            return [f"❌ Número inválido. Tenés {len(tg_sessions)} sesiones (1–{len(tg_sessions)})."]
    except ValueError:
        return [f"❌ Usá `/sessions <número>` (1–{len(tg_sessions)})."]

    target_sid, target_name, _ = tg_sessions[idx]

    # If already active (index 0), do nothing
    if idx == 0:
        return ["⚠️ Ya estás en la sesión activa."]

    # Switching: update telegram_chat_id on target to make it the active one
    # by setting it to the same chat_id and updating its created_at to now
    # (so it becomes the most recent / first in list).
    import time
    current_ts = datetime.now().isoformat()
    async with repos.sessions._transaction() as conn:
        await conn.execute(
            "UPDATE sessions SET created_at = ? WHERE session_id = ?",
            (current_ts, target_sid),
        )
    logger.info("Switched to session %s for chat %d", target_sid, chat_id)
    return [f"✅ Cambiaste a la sesión `{target_sid[:12]}...`"]


# ─── Persistence ───────────────────────────────────────────────────────

async def _persist_conversation(
    session_id: str,
    user_text: str,
    assistant_text: str,
    reasoning: str,
    phases: str,
    li: _LazyImports,
) -> None:
    """Save the assistant message to SQLite (with reasoning + phases for web UI).

    The user message was saved before streaming started.
    Raises on DB failure (error propagates to caller instead of
    being silently swallowed).
    """
    repos = li.get_repos()
    model = li.get_default_model()
    await repos.messages.save_record(li.MessageRecord(
        session_id=session_id,
        role="assistant",
        content=assistant_text,
        model=model,
        reasoning=reasoning,
        phases=phases,
    ))
    logger.info("Persisted TG conversation to session %s", session_id)
    # Notify web UI via SSE (non-critical — failure is just a warning)
    try:
        import httpx
        async with httpx.AsyncClient() as sse_client:
            await sse_client.post(
                _get_sse_notify_url(),
                json={
                    "type": "new_message",
                    "data": {
                        "session_id": session_id,
                        "role": "assistant",
                        "content": assistant_text,
                        "reasoning": reasoning,
                        "phases": phases,
                        "ts": int(time.time()),
                    },
                },
                timeout=3,
            )
    except Exception:
        logger.warning("SSE notify failed (assistant msg): %s", _get_sse_notify_url())


# ─── Lazy imports helper ───────────────────────────────────────────────

async def _persist_partial_conversation(
    session_id: str,
    user_text: str,
    partial_text: str,
    reasoning: str,
    li: _LazyImports,
) -> None:
    """Save partial assistant data when streaming is interrupted
    (error, timeout, or cancellation). Ensures the user sees partial
    reasoning/content on reload instead of just tool pills."""
    try:
        repos = li.get_repos()
        model = li.get_default_model()
        await repos.messages.save_record(li.MessageRecord(
            session_id=session_id,
            role="assistant",
            content=partial_text,
            model=model,
            reasoning=reasoning or "",
            phases="[]",
        ))
        logger.info("Saved partial TG conversation to session %s (%d chars)",
                     session_id, len(partial_text))
    except Exception as e:
        logger.warning("Failed to persist partial TG conversation: %s", e)


class _LazyImports:
    """Lazy imports from src.api — avoids module-level coupling to the core.

    Imports are deferred to the first call, which happens inside an async
    function. This is a structural pattern to keep module-level imports
    free of core dependencies (which may not be loaded yet at import time).
    """

    def __init__(self) -> None:
        self._loaded = False

    def _ensure(self) -> None:
        if self._loaded:
            return
        from src.api import (
            MessageRecord,
            build_system_prompt,
            chat_stream,
            get_default_model,
            get_repos,
        )
        self.MessageRecord = MessageRecord
        self.build_system_prompt = build_system_prompt
        self.chat_stream = chat_stream
        self.get_default_model = get_default_model
        self.get_repos = get_repos
        self._loaded = True

    def __getattr__(self, name: str):
        self._ensure()
        return getattr(self, name)
