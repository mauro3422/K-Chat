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

import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator

from channels.telegram.config import TelegramConfig

logger = logging.getLogger(__name__)

# ─── Channel marker ────────────────────────────────────────────────────
CHANNEL_SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "---\n"
        "Current channel: Telegram\n"
        "You have FULL access to all tools. No limitations.\n"
        "Be concise and direct. Markdown works in Telegram.\n"
        "---"
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

    # ── Commands ────────────────────────────────────────────────────────
    if text == "/start":
        yield (
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
            "**Comandos:**\n"
            "/new — Nueva sesión\n"
            "/reset — Reiniciar\n"
            "/help — Ayuda\n\n"
            "Tengo herramientas, memoria, búsqueda web y más."
        )
        return

    if text in ("/new", "/reset"):
        _reset_session(chat_id, _late_imports)
        yield "✅ Sesión reiniciada."
        return

    if text.startswith("__voice__:"):
        yield "🎤 Mensaje de voz recibido. Transcripción próximamente."
        return

    # ── Save user message ───────────────────────────────────────────────
    try:
        repos = _late_imports.get_repos()
        repos.messages.save_record(_late_imports.MessageRecord(
            session_id=session_id,
            role="user",
            content=text,
            model=model,
            reasoning="",
            phases="[]",
        ))
    except Exception as e:
        logger.warning("Failed to persist user message: %s", e)

    # ── Stream processing ───────────────────────────────────────────────
    logger.info("TG[%d] processing: %.60s", chat_id, text)

    try:
        reasoning_buf: list[str] = []
        content_buf: list[str] = []
        reasoning_flush_interval = 20
        content_flush_interval = 15
        start_time = time.time()

        async for event_type, token in _late_imports.chat_stream(
            message_user=f"📱 {text}",
            history=history,
            model=model,
            session_id=session_id,
            tagged=True,
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
                if len(reasoning_buf) == 1:
                    # First token → flush immediately (show user something)
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                elif len(reasoning_buf) % reasoning_flush_interval == 0:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"

            # ── Content ────────────────────────────────────────────────
            elif event_type == "content":
                # Flush any pending reasoning first
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                    reasoning_buf = []
                content_buf.append(token)
                if len(content_buf) == 1:
                    yield f"__content__:{"".join(content_buf)}"
                elif len(content_buf) % content_flush_interval == 0:
                    yield f"__content__:{"".join(content_buf)}"

            # ── Tool call ──────────────────────────────────────────────
            elif event_type == "tool_call":
                try:
                    tc = json.loads(token) if isinstance(token, str) else token
                    name = tc.get("name", tc.get("function", {}).get("name", ""))
                    if name == "_stream_args":
                        continue
                except Exception:
                    name = str(token)[:30]

                # Flush reasoning (shows why the tool was called),
                # discard content (it's always incomplete before a tool)
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                    reasoning_buf = []
                content_buf = []
                yield f"__tool__:{name}"

            # ── Error ──────────────────────────────────────────────────
            elif event_type == "error":
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                if content_buf:
                    yield f"__content__:{"".join(content_buf)}"
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
            if final_content:
                yield f"__content__:{final_content}"
                _persist_conversation(
                    session_id, text, final_content, _late_imports,
                )
                return

        logger.info("TG[%d] no text content generated", chat_id)

    except Exception as e:
        logger.exception("TG[%d] processing error", chat_id)
        yield f"❌ Error: {e}"


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

    # Search for existing Telegram session for this chat by scanning
    # sessions that have the Telegram rename marker
    try:
        all_sessions = repos.sessions.list()
        for s in all_sessions:
            name = ""
            if isinstance(s, dict):
                name = s.get("name", "") or s.get("session_name", "")
                sid = s.get("session_id", "") or s.get("id", "")
            else:
                name = getattr(s, "name", "") or getattr(s, "session_name", "")
                sid = getattr(s, "session_id", "") or getattr(s, "id", "")

            if "📱 Telegram" in name and sid:
                session_id = sid
                break
    except Exception:
        pass

    history: list[dict[str, Any]] = []

    if session_id:
        logger.info("Restored session %s for chat %d", session_id, chat_id)
        repos.sessions.ensure(session_id)
        repos.sessions.rename(session_id, "📱 Telegram")
        # Load history
        try:
            raw = repos.messages.get_session_messages(session_id)
            for row in raw:
                role = row.get("role") if isinstance(row, dict) else getattr(row, "role", "")
                content = row.get("content") if isinstance(row, dict) else getattr(row, "content", "")
                if role and content:
                    history.append({"role": role, "content": content})
        except Exception:
            history = []
    else:
        session_id = f"tele_{uuid.uuid4().hex[:20]}"
        logger.info("New Telegram session %s for chat %d", session_id, chat_id)
        repos.sessions.ensure(session_id)
        repos.sessions.rename(session_id, "📱 Telegram")

    # Always prepend system prompt + channel context
    model = li.get_default_model()
    system_prompt = li.build_system_prompt(model)
    history = [system_prompt, CHANNEL_SYSTEM_MESSAGE] + history
    return session_id, history


def _reset_session(chat_id: int, li: _LazyImports) -> str:
    """Reset the session for a given chat, returning the new session ID."""
    session_id = f"tele_{uuid.uuid4().hex[:20]}"
    repos = li.get_repos()
    repos.sessions.ensure(session_id)
    repos.sessions.rename(session_id, "📱 Telegram")
    logger.info("Reset Telegram session for chat %d -> %s", chat_id, session_id)
    return session_id


# ─── Persistence ───────────────────────────────────────────────────────

def _persist_conversation(
    session_id: str,
    user_text: str,
    assistant_text: str,
    li: _LazyImports,
) -> None:
    """Save the assistant message to SQLite.

    The user message was saved before streaming started.
    """
    try:
        repos = li.get_repos()
        model = li.get_default_model()
        repos.messages.save_record(li.MessageRecord(
            session_id=session_id,
            role="assistant",
            content=assistant_text,
            model=model,
            reasoning="",
            phases="[]",
        ))
        logger.info("Persisted TG conversation to session %s", session_id)
    except Exception as e:
        logger.warning("Failed to persist TG conversation: %s", e)


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
