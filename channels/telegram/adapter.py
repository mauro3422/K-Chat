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

    if text in ("/new", "/reset"):
        await _reset_session(chat_id, _late_imports)
        yield "__content__:✅ Sesión reiniciada."
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
                        "preview": text[:80],
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
                return

        logger.info("TG[%d] no text content generated", chat_id)

    except Exception as e:
        logger.exception("TG[%d] processing error", chat_id)
        yield f"__error__:{e}"


# ─── Session management ────────────────────────────────────────────────

async def _get_or_create_session(
    chat_id: int, li: _LazyImports,
) -> tuple[str, list[dict[str, Any]]]:
    """Get or create a persistent Telegram session.

    Sessions survive bot restarts via the K-Chat memory DB.
    """
    repos = li.get_repos()

    # Try to restore previous session from the sessions table
    # We use a consistent naming scheme: "telegram_{chat_id}"
    session_id = None

    # Find existing Telegram session for this chat_id.
    # get_all() returns tuples: (session_id, first, last, count, user_count, name)
    session_id = None
    session_name = f"Telegram ({chat_id})"
    try:
        all_sessions = await repos.sessions.get_all()
        for s in all_sessions:
            sid = s[0]      # session_id
            name = s[5]     # session name (COALESCE(s.name, ''))
            if name == session_name and sid:
                session_id = sid
                break
    except Exception:
        pass

    history: list[dict[str, Any]] = []

    if session_id:
        logger.info("Restored session %s for chat %d", session_id, chat_id)
        await repos.sessions.ensure(session_id)
        # Load history — get_session_messages returns tuples:
        # (role, content, model, created_at, reasoning, phases, tool_calls, tool_call_id)
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

            # Strip incomplete tool chains: an assistant with tool_calls MUST be
            # followed by tool messages for EACH tool_call_id, otherwise drop it
            # (DeepSeek rejects incomplete chains with 400).
            cleaned: list[dict[str, Any]] = []
            skip_until_user = 0  # how many tool msgs to skip
            for i, msg in enumerate(history):
                if skip_until_user > 0:
                    skip_until_user -= 1
                    continue
                if msg["role"] == "assistant" and msg.get("tool_calls"):
                    needed = len(msg["tool_calls"])
                    # Check that the next N messages are tool responses
                    following = history[i + 1:i + 1 + needed]
                    tool_ids_avail = [
                        m.get("tool_call_id", "") for m in following
                        if m["role"] == "tool"
                    ]
                    if len(tool_ids_avail) < needed:
                        # Incomplete chain — drop this assistant message
                        logger.debug("Drop incomplete tool chain at msg %d (%d/%d tools)",
                                     i, len(tool_ids_avail), needed)
                        continue
                cleaned.append(msg)
            history = cleaned
        except Exception:
            history = []
    else:
        session_id = f"tele_{uuid.uuid4().hex[:20]}"
        logger.info("New Telegram session %s for chat %d", session_id, chat_id)
        await repos.sessions.ensure(session_id)
        await repos.sessions.rename(session_id, session_name)

    # Always prepend system prompt + channel context
    model = li.get_default_model()
    system_prompt = li.build_system_prompt(model)
    history = [system_prompt, CHANNEL_SYSTEM_MESSAGE] + history
    return session_id, history


async def _reset_session(chat_id: int, li: _LazyImports) -> str:
    """Reset the session for a given chat, returning the new session ID."""
    session_id = f"tele_{uuid.uuid4().hex[:20]}"
    session_name = f"Telegram ({chat_id})"
    repos = li.get_repos()
    await repos.sessions.ensure(session_id)
    await repos.sessions.rename(session_id, session_name)
    logger.info("Reset Telegram session for chat %d -> %s", chat_id, session_id)
    return session_id


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
                        "preview": assistant_text[:80],
                    },
                },
                timeout=3,
            )
    except Exception:
        logger.warning("SSE notify failed (assistant msg): %s", _get_sse_notify_url())


# ─── Lazy imports helper ───────────────────────────────────────────────

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
