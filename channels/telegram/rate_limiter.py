"""Rate limiter — throttles edits to respect Telegram's per-message limits.

Telegram enforces a ~20 edits/min limit per message (≈1 edit per 3s).
Exceeding this triggers a 429 "Too Many Requests" response with a
``retry_after`` field.

A typical stream with 3 tools does ~27 edits to the reasoning message
(inline tool status updates) in ~30s — that's ~54 edits/min, nearly 3x
over Telegram's limit. The 3.0s interval keeps us safely within bounds.

This component tracks edits per (chat_id, message_id) pair and enforces
a minimum interval between edits. It also handles 429 backoff globally
per chat.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from channels.telegram.protocols import RateLimiterProtocol

logger = logging.getLogger(__name__)


class RateLimiter:
    """Per-message edit rate limiter with global 429 backoff.

    Defaults to 3.0s between edits on the same message to stay within
    Telegram's ~20 edits/min limit.
    """

    def __init__(self, min_edit_interval: float = 3.0) -> None:
        self._min_interval = min_edit_interval
        # {(chat_id, message_id): last_edit_timestamp}
        self._last_edit: dict[tuple[int, int], float] = {}
        # {chat_id: time_until_allowed}
        self._global_backoff: dict[int, float] = {}

    async def wait_if_needed(self, chat_id: int, message_id: int) -> None:
        """Wait if we're about to hit the rate limit for this message.

        Also checks global backoff (from 429 responses).
        """
        # Global backoff check
        until = self._global_backoff.get(chat_id, 0.0)
        if until > time.time():
            wait = until - time.time()
            logger.info(
                "TG[%d] global backoff: %.1fs remaining", chat_id, wait,
            )
            await asyncio.sleep(wait)

        # Per-message interval check
        key = (chat_id, message_id)
        last = self._last_edit.get(key, 0.0)
        elapsed = time.time() - last
        if elapsed < self._min_interval:
            wait = self._min_interval - elapsed
            await asyncio.sleep(wait)

    async def record_edit(self, chat_id: int, message_id: int) -> None:
        """Record that an edit was made."""
        self._last_edit[(chat_id, message_id)] = time.time()

    async def handle_429(self, chat_id: int, retry_after: int) -> None:
        """Handle a 429 Too Many Requests response.

        Sets a global backoff for this chat.
        """
        wait = max(retry_after, 2.0)
        until = time.time() + wait
        self._global_backoff[chat_id] = until
        logger.warning(
            "TG[%d] 429 rate limited: backing off %.1fs", chat_id, wait,
        )
        await asyncio.sleep(wait)

    def clear_chat(self, chat_id: int) -> None:
        """Clear all rate limit state for a chat (on stream end)."""
        keys_to_remove = [
            k for k in self._last_edit if k[0] == chat_id
        ]
        for k in keys_to_remove:
            del self._last_edit[k]
        self._global_backoff.pop(chat_id, None)
