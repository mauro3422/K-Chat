"""Adapter between Telegram messages and K-Chat core.

Wraps ``src.core.orchestrator.chat_stream()`` to process Telegram messages
through the full tool loop, memory, and LLM pipeline, then sends the
response back via the Telegram API.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Generator

from channels.telegram.config import TelegramConfig

logger = logging.getLogger(__name__)


# ─── Session store (in-memory, ephemeral) ──────────────────────────────
# In a production setup this would be backed by SQLite via src/memory/
_telegram_sessions: dict[int, str] = {}
"""Maps Telegram chat_id → K-Chat session_id."""

_telegram_history: dict[int, list[dict[str, Any]]] = {}
"""Maps chat_id → accumulated message history for the current session."""


def _get_or_create_session(chat_id: int) -> tuple[str, list[dict[str, Any]]]:
    """Get or create a K-Chat session for this Telegram chat."""
    from src.core.orchestrator import generate_session_id

    if chat_id not in _telegram_sessions:
        session_id = generate_session_id()
        _telegram_sessions[chat_id] = session_id
        _telegram_history[chat_id] = []
        logger.info("New Telegram session %s for chat %d", session_id, chat_id)

    return _telegram_sessions[chat_id], _telegram_history[chat_id]


def reset_session(chat_id: int) -> str:
    """Reset the session for a given chat, returning the new session ID."""
    from src.core.orchestrator import generate_session_id

    session_id = generate_session_id()
    _telegram_sessions[chat_id] = session_id
    _telegram_history[chat_id] = []
    logger.info("Reset Telegram session for chat %d → %s", chat_id, session_id)
    return session_id


def process_message(
    text: str,
    chat_id: int,
    config: TelegramConfig,
) -> Generator[str, None, None]:
    """Process a Telegram message through the K-Chat core pipeline.

    Yields response text chunks as they are generated (streaming).
    """
    from src.core.orchestrator import chat_stream, generate_session_id
    from src.migration_runner import run_pending_migrations

    # Ensure DB is ready
    run_pending_migrations()

    session_id, history = _get_or_create_session(chat_id)

    # Resolve default model
    from src.llm.selector import get_default_model
    model = get_default_model()

    # Handle special commands
    if text == "/start":
        yield (
            "¡Hola! 🦞 Soy **Kairos**, tu asistente personal.\n\n"
            "Comandos disponibles:\n"
            "• /new — Nueva conversación\n"
            "• /reset — Reiniciar sesión actual\n"
            "• /help — Esta ayuda\n\n"
            "¡Mandame un mensaje y charlamos!"
        )
        return

    if text == "/help":
        yield (
            "**Comandos:**\n"
            "• /new — Empezar de cero (nueva sesión)\n"
            "• /reset — Limpiar el contexto actual\n"
            "• /help — Mostrar esta ayuda\n\n"
            "Podés mandarme texto, código, o lo que necesites. "
            "Tengo acceso a 21 herramientas, memoria persistente, "
            "búsqueda web y más."
        )
        return

    if text == "/new":
        new_id = reset_session(chat_id)
        yield f"🆕 Nueva sesión creada: `{new_id[:8]}...`\n\n¿En qué puedo ayudarte?"
        return

    if text == "/reset":
        new_id = reset_session(chat_id)
        yield f"🔄 Sesión reiniciada. Todo fresco. ¿Qué necesitás?"
        return

    # Voice message placeholder
    if text.startswith("__voice__:"):
        yield (
            "🎤 Recibí tu mensaje de voz. "
            "La transcripción automática estará disponible próximamente."
        )
        return

    # ── Normal message: run through core ────────────────────────────────
    logger.info("Telegram[%d] processing: %.60s", chat_id, text)

    try:
        # Accumulate the full response from the stream
        full_response_parts: list[str] = []

        for event_type, token in chat_stream(
            message_user=text,
            history=history,
            model=model,
            session_id=session_id,
            tagged=True,
        ):
            if event_type == "content":
                full_response_parts.append(token)
                # Yield in chunks for progressive delivery
                if len(full_response_parts) % 5 == 0:
                    yield "".join(full_response_parts)

            elif event_type == "reasoning":
                pass  # Don't send reasoning tokens to Telegram

            elif event_type == "tool_call":
                # Tool calls are transparent to the user
                pass

            elif event_type == "error":
                logger.error("Telegram[%d] core error: %s", chat_id, token)
                yield f"❌ Ocurrió un error: {token}"

            elif event_type == "heartbeat":
                pass

        # Send the complete response
        full_response = "".join(full_response_parts)
        if full_response:
            # Update local history
            _telegram_history[chat_id].append({"role": "user", "content": text})
            _telegram_history[chat_id].append({"role": "assistant", "content": full_response})
            yield full_response
        else:
            yield "⚠️ No generé una respuesta. ¿Podés reformular?"

    except Exception as e:
        logger.exception("Telegram[%d] processing error", chat_id)
        yield f"❌ Error interno: {e}"
