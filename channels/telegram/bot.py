"""Telegram bot main loop — polling mode.

Polls the Telegram API for updates and dispatches them through the K-Chat
core pipeline. Runs as a asynchronous loop designed for systemd supervision.

Offset (update_id) is persisted to ``.kairos/telegram_offset`` so the bot
resumes cleanly after a restart.
"""

from __future__ import annotations

import json
import logging
import asyncio
from pathlib import Path
from typing import Any

import httpx

from channels.telegram.config import TelegramConfig
from channels.telegram.handlers import dispatch

logger = logging.getLogger(__name__)

_stop_event = asyncio.Event()
_OFFSET_FILE = Path(__file__).resolve().parent.parent.parent / ".kairos" / "telegram_offset"


# ─── API Helpers ───────────────────────────────────────────────────────

def _api_url(config: TelegramConfig, method: str) -> str:
    return f"{config.api_base}/bot{config.bot_token}/{method}"


async def _api_result(client: httpx.AsyncClient, config: TelegramConfig, method: str, payload: dict) -> dict | None:
    url = _api_url(config, method)
    try:
        resp = await client.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data
        logger.warning("Telegram %s failed (%d): %s", method, resp.status_code, resp.text[:200])
        return None
    except httpx.RequestError as e:
        logger.warning("Telegram %s error: %s", method, e)
        return None


async def _send_message(client: httpx.AsyncClient, config: TelegramConfig, chat_id: int, text: str, parse_mode: str = "Markdown") -> dict | None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    result = await _api_result(client, config, "sendMessage", payload)
    if result is not None:
        return result
    if parse_mode:
        payload.pop("parse_mode", None)
        return await _api_result(client, config, "sendMessage", payload)
    return None


async def _send_action(client: httpx.AsyncClient, config: TelegramConfig, chat_id: int, action: str = "typing") -> None:
    url = _api_url(config, "sendChatAction")
    try:
        await client.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
    except httpx.RequestError:
        pass


# ─── Offset persistence ────────────────────────────────────────────────

def _load_offset() -> int | None:
    try:
        if _OFFSET_FILE.exists():
            val = _OFFSET_FILE.read_text().strip()
            if val.isdigit():
                return int(val)
    except Exception:
        pass
    return None


def _save_offset(offset: int) -> None:
    try:
        _OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
        _OFFSET_FILE.write_text(str(offset))
    except Exception:
        pass


# ─── Telegram polling ──────────────────────────────────────────────────

async def _get_updates(client: httpx.AsyncClient, config: TelegramConfig, offset: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "timeout": 10,
        "allowed_updates": json.dumps(["message", "edited_message"]),
    }
    if offset is not None:
        params["offset"] = offset
    url = _api_url(config, "getUpdates")
    try:
        resp = await client.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
        logger.warning("Telegram getUpdates error: %s", resp.text[:200])
        return []
    except httpx.RequestError as e:
        logger.warning("Telegram getUpdates network error: %s", e)
        return []


def _is_allowed(chat_id: int, config: TelegramConfig) -> bool:
    if not config.allowed_users:
        return True
    return chat_id in config.allowed_users


# ─── Message streaming to Telegram UI ──────────────────────────────────

async def _process_message_stream(client: httpx.AsyncClient, config: TelegramConfig, chat_id: int, text: str, process_fn) -> None:
    """Stream a message through core pipeline and render to Telegram as messages.

    Sequential message flow (each event gets its own Telegram message):
    - __reasoning__ : one msg, edited while thinking. RESET after a tool call.
    - __tool__      : new msg per tool call (always fresh).
    - __content__   : one msg per phase, edited while writing. RESET after a tool.
    - __error__     : error msg, then stop.

    All editing uses plain text to avoid markdown entity errors mid-stream.
    """
    reasoning_msg_id = None
    content_msg_id = None
    current_phase = ""

    async for chunk in process_fn(text, chat_id, config):
        if chunk is None:
            continue

        # ── Reasoning ──────────────────────────────────────────────────
        if chunk.startswith("__reasoning__:"):
            rt = chunk.split(":", 1)[1]
            current_phase = "reasoning"
            display = f"🤔 Pensando...\n\n{rt}"

            if reasoning_msg_id is None:
                resp = await _api_result(client, config, "sendMessage", {
                    "chat_id": chat_id, "text": display, "parse_mode": "",
                })
                if resp:
                    reasoning_msg_id = resp["result"]["message_id"]
                    logger.info("TG[%d] NEW reasoning msg #%s", chat_id, reasoning_msg_id)
            else:
                await _api_result(client, config, "editMessageText", {
                    "chat_id": chat_id, "message_id": reasoning_msg_id,
                    "text": display, "parse_mode": "",
                })

        # ── Tool call ──────────────────────────────────────────────────
        elif chunk.startswith("__tool__:"):
            tool_name = chunk.split(":", 1)[1]
            current_phase = "tool"

            # Reset both so next reasoning/content are NEW messages
            reasoning_msg_id = None
            content_msg_id = None
            await _api_result(client, config, "sendMessage", {
                "chat_id": chat_id, "text": f"🔧 *{tool_name}*", "parse_mode": "Markdown",
            })

        # ── Content ────────────────────────────────────────────────────
        elif chunk.startswith("__content__:"):
            ct = chunk.split(":", 1)[1]

            if current_phase == "tool" or content_msg_id is None:
                # New content phase → send new message
                resp = await _api_result(client, config, "sendMessage", {
                    "chat_id": chat_id, "text": ct, "parse_mode": "",
                })
                if resp:
                    content_msg_id = resp["result"]["message_id"]
                    logger.info("TG[%d] NEW content msg #%s (%d chars)", chat_id, content_msg_id, len(ct))
            else:
                # Same content phase → edit in place
                await _api_result(client, config, "editMessageText", {
                    "chat_id": chat_id, "message_id": content_msg_id,
                    "text": ct, "parse_mode": "",
                })

            current_phase = "content"

        # ── Error ──────────────────────────────────────────────────────
        elif chunk.startswith("__error__:"):
            err = chunk.split(":", 1)[1]
            await _api_result(client, config, "sendMessage", {
                "chat_id": chat_id, "text": f"❌ Error: {err}",
            })
            break
    logger.info("TG[%d] stream complete (reasoning=%s, content=%s)", chat_id, reasoning_msg_id, content_msg_id)


# ─── Main loop ─────────────────────────────────────────────────────────

async def run_bot(config: TelegramConfig) -> None:
    """Main bot loop. Blocks until stop signal or fatal error."""
    if not config.enabled:
        logger.warning("Telegram bot not enabled: TELEGRAM_BOT_TOKEN not set")
        print("[Telegram] ❌ Not enabled. Set TELEGRAM_BOT_TOKEN to activate.")
        return

    logger.info("Telegram bot starting (polling interval: %.1fs)", config.poll_interval)
    print(f"[Telegram] ✅ Bot started. Polling every {config.poll_interval}s")
    print("[Telegram]   Commands: /start /help /new /reset")

    last_update_id: int | None = _load_offset()
    if last_update_id:
        logger.info("Resuming from update offset %d", last_update_id)

    consecutive_errors = 0

    async with httpx.AsyncClient() as client:
        while not _stop_event.is_set():
            try:
                updates = await _get_updates(client, config, last_update_id)

                if not updates:
                    consecutive_errors = max(0, consecutive_errors - 1)
                    try:
                        await asyncio.wait_for(_stop_event.wait(), timeout=config.poll_interval)
                    except asyncio.TimeoutError:
                        pass
                    continue

                consecutive_errors = 0

                for update in updates:
                    if _stop_event.is_set():
                        break

                    update_id = update.get("update_id")
                    if update_id is not None:
                        last_update_id = update_id + 1
                        _save_offset(last_update_id)

                    result = dispatch(update)
                    if result is None:
                        continue

                    text, info = result
                    chat_id = info.get("chat_id")
                    if not chat_id:
                        continue

                    if not _is_allowed(chat_id, config):
                        await _api_result(client, config, "sendMessage", {
                            "chat_id": chat_id, "text": "⛔ No estás autorizado.",
                        })
                        continue

                    logger.info("TG[%d] message: %.60s", chat_id, text)
                    await _send_action(client, config, chat_id, "typing")

                    from channels.telegram.adapter import process_message
                    await _process_message_stream(client, config, chat_id, text, process_message)

                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                logger.info("Telegram bot interrupted")
                break
            except Exception as e:
                consecutive_errors += 1
                delay = min(1.0 * (1.5 ** consecutive_errors), 30.0)
                logger.exception("TG error (attempt %d, retry in %.1fs)", consecutive_errors, delay)
                if consecutive_errors >= 10:
                    logger.critical("Too many errors, shutting down")
                    print("[Telegram] ❌ Fatal error")
                    break
                try:
                    await asyncio.wait_for(_stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass

    logger.info("Telegram bot stopped")
    print("[Telegram] ⏹ Bot stopped.")


def stop() -> None:
    """Signal the bot to shut down gracefully."""
    _stop_event.set()
