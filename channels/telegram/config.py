"""Telegram channel configuration — read from env / config loader."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class TelegramConfig:
    """Immutable Telegram bot configuration."""

    bot_token: str = ""
    allowed_users: list[int] = field(default_factory=list)
    poll_interval: float = 1.0
    webhook_url: str = ""
    api_base: str = "https://api.telegram.org"
    session_timeout_minutes: int = 30

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token)


def load_telegram_config() -> TelegramConfig:
    """Load config from environment variables."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_raw = os.getenv("TELEGRAM_ALLOWED_USERS", "").strip()
    allowed: list[int] = []
    if allowed_raw:
        for part in allowed_raw.split(","):
            part = part.strip()
            if part.isdigit():
                allowed.append(int(part))

    poll_interval = float(os.getenv("TELEGRAM_POLL_INTERVAL", "1.0"))
    webhook = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()

    return TelegramConfig(
        bot_token=token,
        allowed_users=allowed,
        poll_interval=max(0.1, poll_interval),
        webhook_url=webhook,
    )
