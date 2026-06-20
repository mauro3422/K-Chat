"""Telegram channel adapter for K-Chat.

Connects a Telegram bot to the K-Chat core engine (``src.core.orchestrator``).
Messages received via polling are processed by the tool loop and replied to
through the Telegram API.

Usage:
    python -m channels.telegram              # start polling
    python -m channels.telegram --help       # show options

Environment variables:
    TELEGRAM_BOT_TOKEN       — Bot token from BotFather (required)
    TELEGRAM_ALLOWED_USERS   — Comma-separated user IDs (empty = allow all)
    TELEGRAM_POLL_INTERVAL   — Seconds between polls (default: 1.0)
    TELEGRAM_WEBHOOK_URL     — If set, use webhook mode instead of polling
"""

from __future__ import annotations

import asyncio
from src.config_loader import load_config
from channels.telegram.config import load_telegram_config
from channels.telegram.bot import run_bot

DEFINITION = {
    "name": "telegram",
    "description": "Telegram bot — two-way conversation via core.chat_stream()",
    "version": "0.1.0",
    "author": "Kairos",
    "dependencies": ["httpx"],
}


def run() -> None:
    """Start the Telegram bot (blocking polling loop).

    This is the entry point used by the channel registry / CLI dispatcher.
    """
    config = load_telegram_config()
    cluster_cfg = load_config()
    if getattr(cluster_cfg, "peer_urls", "").strip() and getattr(cluster_cfg, "node_role", "secondary") != "primary":
        print("⚠️ Telegram bot disabled on secondary node.")
        return
    asyncio.run(run_bot(config))


def stop() -> None:
    """Signal the bot to shut down gracefully."""
    import channels.telegram.bot as bot_mod
    bot_mod._stop_event.set()
