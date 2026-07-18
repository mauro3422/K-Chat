"""Telegram bot main loop — polling mode.

Polls the Telegram API for updates and dispatches them through the
K-Chat core pipeline. The rendering of stream events to Telegram
messages is delegated to ``TelegramRenderer``.

Offset (``update_id``) is persisted to ``.kairos/telegram_offset`` so
the bot resumes cleanly after a restart.

Logs are written to:
  - stderr (console) via systemd journal
  - ``logs/server/YYYY-MM-DD.jsonl`` via JsonlHandler (rotated daily)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from channels.telegram.api_client import TelegramAPIClient
from channels.telegram.char_splitter import CharSplitter
from channels.telegram.config import TelegramConfig
from channels.telegram.error_handler import TelegramErrorHandler
from channels.telegram.handlers import dispatch
from channels.telegram.message_manager import MessageManager
from channels.telegram.rate_limiter import RateLimiter
from channels.telegram.renderer import TelegramRenderer
from channels.telegram.ws_client import BotWSClient
from src.config_loader import load_config
from src.memory.repos.telegram_msg_id_repository import TelegramMsgIdRepo
from web.services.file_logger import install_jsonl_handler

logger = logging.getLogger(__name__)

_stop_event = asyncio.Event()

# Max consecutive errors before shutting down
_MAX_CONSECUTIVE_ERRORS = 10


async def _warmup_provider() -> int:
    """Reset provider state and verify that the configured backend responds."""
    from src.llm.providers import _get_provider, reset_registry

    reset_registry()
    provider = _get_provider()
    models = await provider.list_models()
    return len(models)


# ─── Main loop ─────────────────────────────────────────────────────────

async def run_bot(config: TelegramConfig) -> None:
    """Main bot loop. Blocks until stop signal or fatal error."""
    if not config.enabled:
        logger.warning("Telegram bot not enabled: TELEGRAM_BOT_TOKEN not set")
        print("[Telegram] ❌ Not enabled. Set TELEGRAM_BOT_TOKEN to activate.")
        return

    # ── File logging (rotated daily) ────────────────────────────────────
    try:
        install_jsonl_handler("channels.telegram")
    except Exception:
        pass

    logger.info("Telegram bot starting (polling interval: %.1fs)", config.poll_interval)
    print(f"[Telegram] ✅ Bot started. Polling every {config.poll_interval}s")
    print("[Telegram]   Commands: /start /help /new /reset")

    # ── WebSocket connection for live token streaming ─────────────────
    ws_client = BotWSClient()
    await ws_client.connect()

    # ── Warmup: preheat httpx connection pool ──────────────────────────
    try:
        model_count = await _warmup_provider()
        logger.info("Warmup OK: %d models available", model_count)
    except Exception as we:
        logger.warning("Warmup failed (non-fatal): %s", we)

    # ── Build Lego components ──────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        api_client = TelegramAPIClient(client, config)
        message_manager = MessageManager(repo=TelegramMsgIdRepo())
        rate_limiter = RateLimiter()
        char_splitter = CharSplitter()
        error_handler = TelegramErrorHandler()

        renderer = TelegramRenderer(
            api_client=api_client,
            message_manager=message_manager,
            rate_limiter=rate_limiter,
            char_splitter=char_splitter,
            error_handler=error_handler,
        )

        last_update_id: int | None = TelegramAPIClient._load_offset()
        if last_update_id:
            logger.info("Resuming from update offset %d", last_update_id)

        consecutive_errors = 0

        while not _stop_event.is_set():
            try:
                updates = await api_client.get_updates(last_update_id)

                if not updates:
                    consecutive_errors = max(0, consecutive_errors - 1)
                    try:
                        await asyncio.wait_for(
                            _stop_event.wait(), timeout=config.poll_interval,
                        )
                    except asyncio.TimeoutError:
                        pass
                    continue

                consecutive_errors = 0

                tasks = []
                for update in updates:
                    if _stop_event.is_set():
                        break

                    update_id = update.get("update_id")
                    if update_id is not None:
                        last_update_id = update_id + 1
                        TelegramAPIClient._save_offset(last_update_id)

                    # Process updates concurrently — multiple Telegram
                    # sessions can run in parallel
                    tasks.append(
                        _process_single_update(api_client, renderer, config, update),
                    )

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                logger.info("Telegram bot interrupted")
                break
            except Exception as e:
                consecutive_errors += 1
                delay = min(1.0 * (1.5 ** consecutive_errors), 30.0)
                logger.exception(
                    "TG loop error (attempt %d, retry in %.1fs)",
                    consecutive_errors, delay,
                )
                if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                    logger.critical("Too many errors, shutting down")
                    print("[Telegram] ❌ Fatal error — too many consecutive failures.")
                    break
                try:
                    await asyncio.wait_for(
                        _stop_event.wait(), timeout=delay,
                    )
                except asyncio.TimeoutError:
                    pass

    logger.info("Telegram bot stopped")
    print("[Telegram] ⏹ Bot stopped.")


# ─── Single update processing ──────────────────────────────────────────

async def _process_single_update(
    api_client: TelegramAPIClient,
    renderer: TelegramRenderer,
    config: TelegramConfig,
    update: dict[str, Any],
) -> None:
    """Dispatch and process a single Telegram update."""
    result = dispatch(update)
    if result is None:
        return

    text, info = result
    chat_id = info.get("chat_id")
    if not chat_id:
        return

    if not _is_allowed(chat_id, config):
        await api_client.send_message(
            chat_id, "⛔ No estás autorizado.",
        )
        return

    logger.info("TG[%d] message: %.60s", chat_id, text)

    # ── Clear command: delete all messages in chat visually ───────────
    if text in ("/new", "/reset", "/clear", "/delete"):
        await _clear_chat_messages(api_client, renderer, chat_id)

    # ── /clear skips the LLM (visual only, nothing to process) ────────
    if text == "/clear":
        await api_client.send_message(chat_id, "🧹 Chat limpiado.")
        return

    await api_client.send_action(chat_id, "typing")

    from channels.telegram.adapter import process_message
    await renderer.render_stream(chat_id, process_message(text, chat_id, config, ws_client))


# ─── Authorization ─────────────────────────────────────────────────────

def _is_allowed(chat_id: int, config: TelegramConfig) -> bool:
    if not config.allowed_users:
        return True
    return chat_id in config.allowed_users


# ─── Clear chat messages ──────────────────────────────────────────────

async def _clear_chat_messages(
    api_client: "TelegramAPIClient",
    renderer: "TelegramRenderer",
    chat_id: int,
) -> None:
    """Delete all tracked messages for a chat (visual clear).

    Gets all stored message IDs from the renderer's MessageManager
    and deletes them via the Telegram API. Also clears the manager state.

    Note: only messages whose IDs were persisted to SQLite can be deleted.
    Messages sent before the ``telegram_msg_ids`` migration was deployed
    (2026-06-15) won't have their IDs tracked and can't be recovered.
    """
    count = 0
    mm = renderer._mm  # MessageManager instance
    all_ids = await mm.get_all_msg_ids(chat_id)
    logger.info(
        "TG clear: found %d tracked message IDs for chat %d",
        len(all_ids), chat_id,
    )
    for msg_id in all_ids:
        try:
            ok = await api_client.delete_message(chat_id, msg_id)
            if ok:
                count += 1
            else:
                logger.debug("TG delete_message returned False for msg %d", msg_id)
        except Exception as e:
            logger.debug("TG delete_message error for msg %d: %s", msg_id, e)

    await mm.cleanup(chat_id)
    if count > 0:
        logger.info("TG clear: deleted %d messages for chat %d", count, chat_id)


# ─── Shutdown ──────────────────────────────────────────────────────────

def stop() -> None:
    """Signal the bot to shut down gracefully."""
    _stop_event.set()
