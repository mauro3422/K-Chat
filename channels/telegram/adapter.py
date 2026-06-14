"""Adapter between Telegram messages and K-Chat core.

Wraps ``src.core.orchestrator.chat_stream()`` to process Telegram messages
through the full tool loop, memory, and LLM pipeline, then sends the
response back via the Telegram API.

Telegram sessions are persistent across bot restarts via a JSON mapping file
at ``.kairos/telegram_sessions.json``.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator

from channels.telegram.config import TelegramConfig

logger = logging.getLogger(__name__)

# ─── Persistent session store ──────────────────────────────────────────
_SESSION_FILE = Path(__file__).resolve().parent.parent.parent / ".kairos" / "telegram_sessions.json"


def _load_sessions() -> dict[str, str]:
    """Load persistent chat_id → session_id mapping."""
    try:
        if _SESSION_FILE.exists():
            data = json.loads(_SESSION_FILE.read_text())
            return {str(k): v for k, v in data.items()}
    except Exception as e:
        logger.warning("Failed to load sessions file: %s", e)
    return {}


def _save_session(chat_id: int, session_id: str) -> None:
    """Persist chat_id → session_id mapping to disk."""
    try:
        _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = _load_sessions()
        data[str(chat_id)] = session_id
        _SESSION_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.warning("Failed to save session mapping: %s", e)


# ─── Channel marker ────────────────────────────────────────────────────
CHANNEL_SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "---\n"
        "Current channel: Telegram\n"
        "You have FULL access to all tools. No limitations.\n"
        "Be concise and direct. Markdown works in Telegram.\n"
        "---"
    )
}


def _make_telegram_session_id() -> str:
    return f"tele_{uuid.uuid4().hex[:20]}"


async def get_or_create_session(chat_id: int) -> tuple[str, list[dict[str, Any]]]:
    """Get or create a persistent Telegram session.

    Session mapping is saved to disk so it survives bot restarts.
    Builds full history with system prompt + channel context.
    """
    from src.memory.repos import get_repos
    from src.context.builder import build_system_prompt
    from src.llm.selector import get_default_model

    repos = get_repos()

    # Try to restore previous session
    sessions = _load_sessions()
    chat_key = str(chat_id)
    history: list[dict[str, Any]] = []

    if chat_key in sessions:
        session_id = sessions[chat_key]
        logger.info("Restored session %s for chat %d", session_id, chat_id)
        # Ensure session exists in DB (survives bot restarts)
        repos.sessions.ensure(session_id)
        # Rename so it shows nicely in sidebar
        repos.sessions.rename(session_id, "📱 Telegram")
        try:
            raw = repos.messages.get_session_messages(session_id) if hasattr(repos, 'messages') else []
            for row in raw:
                role = row.get("role") if isinstance(row, dict) else getattr(row, "role", "")
                content = row.get("content") if isinstance(row, dict) else getattr(row, "content", "")
                if role and content:
                    history.append({"role": role, "content": content})
        except Exception:
            history = []
    else:
        session_id = _make_telegram_session_id()
        _save_session(chat_id, session_id)
        logger.info("New Telegram session %s for chat %d", session_id, chat_id)
        repos.sessions.ensure(session_id)
        repos.sessions.rename(session_id, "📱 Telegram")
    # Always prepend system prompt + channel context
    model = get_default_model()
    system_prompt = build_system_prompt(model)
    history = [system_prompt, CHANNEL_SYSTEM_MESSAGE] + history
    return session_id, history

def reset_session(chat_id: int) -> str:
    """Reset the session for a given chat, returning the new session ID."""
    from src.memory.repos import get_repos

    session_id = _make_telegram_session_id()
    _save_session(chat_id, session_id)

    repos = get_repos()
    repos.sessions.ensure(session_id)
    repos.sessions.rename(session_id, "📱 Telegram")

    logger.info("Reset Telegram session for chat %d -> %s", chat_id, session_id)
    return session_id


async def process_message(
    text: str,
    chat_id: int,
    config: TelegramConfig,
) -> AsyncGenerator[str, None]:
    """Process a Telegram message through the K-Chat core pipeline.

    Yields tagged messages for bot.py to display:
    ``__reasoning__:<text>``, ``__content__:<text>``, ``__tool__:<name>``, ``__error__:<msg>``
    """
    from src.core.orchestrator import chat_stream

    session_id, history = await get_or_create_session(chat_id)

    from src.llm.selector import get_default_model
    from src.memory.repos import get_repos
    from src.memory.repos.message_repository import MessageRecord

    model = get_default_model()

    # ── Commands (BEFORE saving user message) ────────────────────────
    if text == "/start":
        yield "¡Hola! Soy **Kairos**, tu asistente personal.\n\nComandos:\n/new — Nueva sesión\n/reset — Reiniciar\n/help — Ayuda\n\nMandame lo que necesites."
        return
    if text == "/help":
        yield "**Comandos:**\n/new — Nueva sesión\n/reset — Reiniciar\n/help — Ayuda\n\nTengo herramientas, memoria, búsqueda web y más."
        return
    if text in ("/new", "/reset"):
        reset_session(chat_id)
        yield "Sesion reiniciada."
        return
    if text.startswith("__voice__:"):
        yield "Mensaje de voz recibido. Transcripcion proximamente."
        return

    # Save user message AFTER command check (only real messages)
    try:
        repos = get_repos()
        repos.messages.save_record(MessageRecord(
            session_id=session_id,
            role="user",
            content=text,
            model=model,
            reasoning="", phases="[]",
        ))
    except Exception as e:
        logger.warning("Failed to persist user message: %s", e)

    # ── Normal message ──────────────────────────────────────────────────
    logger.info("Telegram[%d] processing: %.60s", chat_id, text)

    try:
        reasoning_buf: list[str] = []
        content_buf: list[str] = []
        last_phase: str = ""
        start_time = time.time()
        timeout_seconds = 120

        async for event_type, token in chat_stream(
            message_user=f"📱 {text}",
            history=history,
            model=model,
            session_id=session_id,
            tagged=True,
        ):
            if time.time() - start_time > timeout_seconds:
                if content_buf:
                    yield f"__content__:{"".join(content_buf)}"
                elif reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                else:
                    yield "Operacion agotada. Mandame el mensaje de nuevo."
                return

            if event_type == "reasoning":
                # First reasoning token? Flush immediately
                if not reasoning_buf:
                    reasoning_buf.append(token)
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                else:
                    reasoning_buf.append(token)
                last_phase = "reasoning"
                if len(reasoning_buf) % 20 == 0:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"

            elif event_type == "content":
                if last_phase == "reasoning" and reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                # First content token? Flush immediately
                if not content_buf:
                    content_buf.append(token)
                    yield f"__content__:{"".join(content_buf)}"
                else:
                    content_buf.append(token)
                last_phase = "content"
                if len(content_buf) % 15 == 0:
                    yield f"__content__:{"".join(content_buf)}"

            elif event_type == "tool_call":
                try:
                    tc = json.loads(token) if isinstance(token, str) else token
                    name = tc.get("name", tc.get("function", {}).get("name", ""))
                    if name == "_stream_args":
                        continue
                except Exception:
                    name = str(token)[:30]

                # Only flush reasoning (shows what led to the tool decision)
                # Do NOT flush content — it's always incomplete before a tool
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                    reasoning_buf = []
                content_buf = []  # Discard incomplete content silently
                yield f"__tool__:{name}"
                last_phase = "tool"

            elif event_type == "error":
                if reasoning_buf:
                    yield f"__reasoning__:{"".join(reasoning_buf)}"
                if content_buf:
                    yield f"__content__:{"".join(content_buf)}"
                yield f"__error__:{token}"
                return

            elif event_type == "heartbeat":
                pass
        # ── Final flush + persist to DB ─────────────────────────────────
        if reasoning_buf:
            yield f"__reasoning__:{"".join(reasoning_buf)}"

        if content_buf:
            final_content = "".join(content_buf).strip()
            if final_content:
                yield f"__content__:{final_content}"
                _persist_conversation(session_id, text, final_content)
                return

        logger.info("Telegram[%d] no text content generated", chat_id)

    except Exception as e:
        logger.exception("Telegram[%d] processing error", chat_id)
        yield f"❌ Error: {e}"

def _persist_conversation(session_id: str, user_text: str, assistant_text: str) -> None:
    """Save the assistant message to SQLite so it appears in the web UI sidebar.
    
    The user message was already saved before streaming started.
    """
    try:
        from src.memory.repos import get_repos
        from src.memory.repos.message_repository import MessageRecord
        from src.llm.selector import get_default_model

        repos = get_repos()
        model = get_default_model()

        # Save assistant message (user message was saved before streaming)
        repos.messages.save_record(MessageRecord(
            session_id=session_id,
            role="assistant",
            content=assistant_text,
            model=model,
            reasoning="",
            phases="[]",
        ))

        logger.info("Persisted Telegram conversation to session %s", session_id)
    except Exception as e:
        logger.warning("Failed to persist Telegram conversation: %s", e)
