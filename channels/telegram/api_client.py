"""Telegram API client — wraps httpx calls to the Telegram Bot API.

Provides send_message, edit_message, and send_action as the low-level
building blocks for the Telegram channel renderer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from channels.telegram.config import TelegramConfig

logger = logging.getLogger(__name__)


class TelegramAPIClient:
    """Stateless HTTP client for the Telegram Bot API.

    Thread-safe. Designed to be shared across all chats in a single
    polling loop.
    """

    def __init__(self, client: httpx.AsyncClient, config: TelegramConfig) -> None:
        self._client = client
        self._config = config

    # ── Public API ──────────────────────────────────────────────────────

    async def send_message(
        self, chat_id: int, text: str, parse_mode: str = "",
    ) -> int | None:
        """Send a new message. Returns ``message_id`` or ``None`` on failure.

        Automatically retries without ``parse_mode`` if Markdown fails.
        """
        payload: dict = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        result = await self._api_result("sendMessage", payload)
        if result is not None:
            return result["result"]["message_id"]

        # Retry without parse_mode on failure
        if parse_mode:
            payload.pop("parse_mode", None)
            result = await self._api_result("sendMessage", payload)
            if result is not None:
                return result["result"]["message_id"]

        return None

    async def edit_message(
        self, chat_id: int, message_id: int, text: str, parse_mode: str = "",
    ) -> bool:
        """Edit an existing message. Returns ``True`` on success."""
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        result = await self._api_result("editMessageText", payload)
        if result is not None:
            return True

        # Retry without parse_mode
        if parse_mode:
            payload.pop("parse_mode", None)
            result = await self._api_result("editMessageText", payload)
            if result is not None:
                return True

        return False

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete a message via ``deleteMessage``. Returns ``True`` on success."""
        try:
            result = await self._api_result("deleteMessage", {
                "chat_id": chat_id,
                "message_id": message_id,
            })
            return result is not None
        except Exception as e:
            logger.debug("TG deleteMessage error (chat=%d, msg=%d): %s", chat_id, message_id, e)
            return False

    async def send_action(self, chat_id: int, action: str = "typing") -> None:
        """Send a chat action (typing indicator). Errors are logged only."""
        try:
            await self._client.post(
                self._url("sendChatAction"),
                json={"chat_id": chat_id, "action": action},
                timeout=5,
            )
        except httpx.RequestError as e:
            logger.debug("TG sendChatAction error (benign): %s", e)

    # ── Internals ───────────────────────────────────────────────────────

    def _url(self, method: str) -> str:
        return f"{self._config.api_base}/bot{self._config.bot_token}/{method}"

    async def _api_result(self, method: str, payload: dict) -> dict | None:
        """Call a Telegram API method. Returns the full response dict on success."""
        url = self._url(method)
        try:
            resp = await self._client.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data

            # Non-200 or !ok: raise for error handler
            logger.debug(
                "TG %s failed (%d): %.150s",
                method, resp.status_code, resp.text,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError:
            raise
        return None

    # ── Polling helpers (moved from bot.py) ─────────────────────────────

    @staticmethod
    def _load_offset() -> int | None:
        """Load the last processed update offset from disk."""
        path = _offset_file()
        try:
            if path.exists():
                val = path.read_text().strip()
                if val.isdigit():
                    return int(val)
        except Exception:
            pass
        return None

    @staticmethod
    def _save_offset(offset: int) -> None:
        """Persist the last processed update offset to disk."""
        path = _offset_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(offset))
        except Exception:
            pass

    async def get_updates(
        self, offset: int | None = None,
    ) -> list[dict]:
        """Poll for new updates."""
        params: dict = {
            "timeout": 10,
            "allowed_updates": json.dumps(["message", "edited_message"]),
        }
        if offset is not None:
            params["offset"] = offset

        url = self._url("getUpdates")
        try:
            resp = await self._client.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result", [])
            logger.warning("TG getUpdates error: %.200s", resp.text)
            return []
        except httpx.RequestError as e:
            logger.warning("TG getUpdates network: %s", e)
            return []


def _offset_file() -> Path:
    """Path to the persistent offset file."""
    return (
        Path(__file__).resolve().parent.parent.parent
        / ".kairos" / "telegram_offset"
    )
