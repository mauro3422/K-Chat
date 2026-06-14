"""Telegram bot main loop — polling mode.

Polls the Telegram API for updates and dispatches them through the K-Chat
core pipeline. Runs as a blocking loop designed for systemd supervision.
"""

from __future__ import annotations

import json
import logging
import time
import threading
from typing import Any

import requests

from channels.telegram.config import TelegramConfig
from channels.telegram.handlers import dispatch

logger = logging.getLogger(__name__)

# ─── Global stop event ──────────────────────────────────────────────────
_stop_event = threading.Event()


def _api_url(config: TelegramConfig, method: str) -> str:
    """Build Telegram API URL for a method."""
    return f"{config.api_base}/bot{config.bot_token}/{method}"


def _send_message(config: TelegramConfig, chat_id: int, text: str, **kwargs: Any) -> bool:
    """Send a message via Telegram API. Returns True on success."""
    url = _api_url(config, "sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        **kwargs,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning("Telegram send failed (%d): %s", resp.status_code, resp.text[:200])
            # Fallback: send without markdown if parse_mode fails
            if "parse_mode" in kwargs or "parse_mode" not in locals():
                payload.pop("parse_mode", None)
                resp2 = requests.post(url, json=payload, timeout=10)
                if resp2.status_code != 200:
                    return False
        return True
    except requests.RequestException as e:
        logger.warning("Telegram send error: %s", e)
        return False


def _send_chunked(config: TelegramConfig, chat_id: int, text: str) -> None:
    """Send long messages in chunks (Telegram limit: 4096 chars)."""
    max_len = 4000  # Leave room for safety
    if len(text) <= max_len:
        _send_message(config, chat_id, text)
        return

    for i in range(0, len(text), max_len):
        chunk = text[i:i + max_len]
        if not _send_message(config, chat_id, chunk):
            break


def _send_action(config: TelegramConfig, chat_id: int, action: str = "typing") -> None:
    """Send a chat action (typing indicator, etc.)."""
    url = _api_url(config, "sendChatAction")
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
    except requests.RequestException:
        pass


def _get_updates(config: TelegramConfig, offset: int | None = None) -> list[dict[str, Any]]:
    """Fetch updates from Telegram API."""
    url = _api_url(config, "getUpdates")
    params: dict[str, Any] = {"timeout": 10, "allowed_updates": json.dumps(["message", "edited_message"])}
    if offset is not None:
        params["offset"] = offset

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
        logger.warning("Telegram getUpdates error: %s", resp.text[:200])
        return []
    except requests.RequestException as e:
        logger.warning("Telegram getUpdates network error: %s", e)
        return []


def _is_allowed(chat_id: int, config: TelegramConfig) -> bool:
    """Check if this user is allowed to interact with the bot."""
    if not config.allowed_users:
        return True  # Allow all if no restriction
    return chat_id in config.allowed_users


def run_bot(config: TelegramConfig) -> None:
    """Main bot loop. Blocks until stop signal or fatal error."""
    if not config.enabled:
        logger.warning("Telegram bot not enabled: TELEGRAM_BOT_TOKEN not set")
        print("[Telegram] ❌ Not enabled. Set TELEGRAM_BOT_TOKEN to activate.")
        return

    logger.info("Telegram bot starting (polling interval: %.1fs)", config.poll_interval)
    print(f"[Telegram] ✅ Bot started. Polling every {config.poll_interval}s")
    print("[Telegram]   Commands: /start /help /new /reset")

    last_update_id: int | None = None
    retry_delay = 1.0
    consecutive_errors = 0

    while not _stop_event.is_set():
        try:
            updates = _get_updates(config, last_update_id)

            if not updates:
                # No updates — sleep and retry with backoff if errors
                if consecutive_errors > 0:
                    consecutive_errors = max(0, consecutive_errors - 1)
                    retry_delay = min(retry_delay * 0.5, config.poll_interval)
                _stop_event.wait(config.poll_interval)
                continue

            # Reset error count on success
            consecutive_errors = 0
            retry_delay = config.poll_interval

            for update in updates:
                if _stop_event.is_set():
                    break

                # Track the last update ID to acknowledge processed updates
                update_id = update.get("update_id")
                if update_id is not None:
                    last_update_id = update_id + 1

                # Dispatch to handlers
                result = dispatch(update)
                if result is None:
                    continue

                text, info = result
                chat_id = info.get("chat_id")
                if not chat_id:
                    continue

                # Authorization check
                if not _is_allowed(chat_id, config):
                    _send_message(config, chat_id, "⛔ No estás autorizado para usar este bot.")
                    continue

                # Process through core pipeline
                logger.info("Telegram message from %d: %.60s", chat_id, text)
                _send_action(config, chat_id, "typing")

                # Collect full response
                from channels.telegram.adapter import process_message
                response_parts: list[str] = []
                for chunk in process_message(text, chat_id, config):
                    if chunk:
                        response_parts.append(chunk)

                full_response = "".join(response_parts)

                if full_response:
                    _send_chunked(config, chat_id, full_response)
                    logger.info("Telegram response to %d: %d chars", chat_id, len(full_response))
                else:
                    _send_message(config, chat_id, "⚠️ No generé respuesta.")

            # Brief pause between polling cycles
            _stop_event.wait(0.1)

        except KeyboardInterrupt:
            logger.info("Telegram bot interrupted")
            break
        except Exception as e:
            consecutive_errors += 1
            delay = min(retry_delay * (1.5 ** consecutive_errors), 30.0)
            logger.exception("Telegram bot error (attempt %d, retry in %.1fs)", consecutive_errors, delay)
            if consecutive_errors >= 10:
                logger.critical("Too many consecutive errors, shutting down Telegram bot")
                print("[Telegram] ❌ Fatal error - too many consecutive failures")
                break
            _stop_event.wait(delay)

    logger.info("Telegram bot stopped")
    print("[Telegram] ⏹ Bot stopped.")
