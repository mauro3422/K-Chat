"""Message handlers for Telegram updates.

Each handler inspects a Telegram update and decides whether to process it.
Handlers are registered in a simple dispatch table and called in order.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ─── Handler type ───────────────────────────────────────────────────────
HandlerFunc = Callable[[dict[str, Any]], str | None]
"""Takes a Telegram update dict, returns extracted text or None if skip."""

# ─── Registry ───────────────────────────────────────────────────────────
_handlers: list[HandlerFunc] = []


def register(handler: HandlerFunc) -> HandlerFunc:
    """Register a message handler."""
    _handlers.append(handler)
    return handler


def dispatch(update: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Run handlers in order. Returns (text, message_info) or None."""
    for handler in _handlers:
        result = handler(update)
        if result is not None:
            # Extract message metadata
            msg = update.get("message") or update.get("edited_message") or {}
            return result, {
                "chat_id": msg.get("chat", {}).get("id"),
                "message_id": msg.get("message_id"),
                "date": msg.get("date"),
                "from_user": msg.get("from", {}).get("id"),
                "is_command": result.startswith("/"),
            }
    return None


# ─── Built-in handlers ──────────────────────────────────────────────────

@register
def handle_text_message(update: dict[str, Any]) -> str | None:
    """Handle plain text messages."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None
    text = msg.get("text", "").strip()
    if not text:
        return None
    return text


@register
def handle_voice_message(update: dict[str, Any]) -> str | None:
    """Handle voice messages — returns a placeholder for ASR processing.

    Actual transcription requires the ASR bridge (web/routers/asr.py).
    For now, voice messages are acknowledged but not transcribed.
    """
    msg = update.get("message")
    if not msg:
        return None
    voice = msg.get("voice")
    if not voice:
        return None
    # Return a special marker that the adapter can detect
    file_id = voice.get("file_id", "unknown")
    duration = voice.get("duration", 0)
    return f"__voice__:{file_id}:{duration}"


@register
def handle_command_start(update: dict[str, Any]) -> str | None:
    """Handle /start command."""
    msg = update.get("message")
    if not msg:
        return None
    text = msg.get("text", "").strip()
    if text == "/start":
        return "/start"
    return None


@register
def handle_command_help(update: dict[str, Any]) -> str | None:
    """Handle /help command."""
    msg = update.get("message")
    if not msg:
        return None
    text = msg.get("text", "").strip()
    if text == "/help":
        return "/help"
    return None


@register
def handle_command_new(update: dict[str, Any]) -> str | None:
    """Handle /new — start a fresh session."""
    msg = update.get("message")
    if not msg:
        return None
    text = msg.get("text", "").strip()
    if text == "/new":
        return "/new"
    return None


@register
def handle_command_reset(update: dict[str, Any]) -> str | None:
    """Handle /reset — reset current session."""
    msg = update.get("message")
    if not msg:
        return None
    text = msg.get("text", "").strip()
    if text == "/reset":
        return "/reset"
    return None
