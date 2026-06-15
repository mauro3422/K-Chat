"""Tests for the Telegram rate limiter — edit throttle & 429 backoff."""

import asyncio
import time

import pytest

from channels.telegram.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter — timing-sensitive but with short intervals."""

    def setup_method(self):
        self.rl = RateLimiter(min_edit_interval=0.05)  # 50ms for fast tests

    @pytest.mark.asyncio
    async def test_first_edit_no_wait(self):
        """First edit for a message has no wait."""
        t0 = time.time()
        await self.rl.wait_if_needed(123, 1001)
        elapsed = time.time() - t0
        assert elapsed < 0.03  # should be nearly instant

    @pytest.mark.asyncio
    async def test_consecutive_edit_waits(self):
        """Second edit within min_interval waits."""
        await self.rl.record_edit(123, 1001)
        t0 = time.time()
        await self.rl.wait_if_needed(123, 1001)
        elapsed = time.time() - t0
        assert elapsed >= 0.04  # should wait ~50ms

    @pytest.mark.asyncio
    async def test_different_messages_no_wait(self):
        """Different message IDs don't interfere."""
        await self.rl.record_edit(123, 1001)
        t0 = time.time()
        await self.rl.wait_if_needed(123, 1002)
        elapsed = time.time() - t0
        assert elapsed < 0.03

    @pytest.mark.asyncio
    async def test_different_chats_no_wait(self):
        """Different chat IDs don't interfere per-message."""
        await self.rl.record_edit(123, 1001)
        t0 = time.time()
        await self.rl.wait_if_needed(456, 1001)
        elapsed = time.time() - t0
        assert elapsed < 0.03

    @pytest.mark.asyncio
    async def test_429_backoff(self):
        """Global 429 backoff causes wait_if_needed to block."""
        self.rl._global_backoff[123] = time.time() + 2.0
        t0 = time.time()
        await self.rl.wait_if_needed(123, 9999)
        elapsed = time.time() - t0
        assert elapsed >= 1.9  # should wait ~2s

    @pytest.mark.asyncio
    async def test_429_backoff_other_chat_untouched(self):
        """429 backoff for one chat doesn't affect another."""
        self.rl._global_backoff[123] = time.time() + 10.0
        t0 = time.time()
        await self.rl.wait_if_needed(456, 1001)
        elapsed = time.time() - t0
        assert elapsed < 0.03  # different chat, no wait

    @pytest.mark.asyncio
    async def test_clear_chat_removes_all(self):
        """clear_chat removes per-message state and backoff."""
        await self.rl.record_edit(123, 1001)
        await self.rl.record_edit(123, 1002)
        self.rl._global_backoff[123] = time.time() + 10
        self.rl.clear_chat(123)
        assert (123, 1001) not in self.rl._last_edit
        assert (123, 1002) not in self.rl._last_edit
        assert 123 not in self.rl._global_backoff

    @pytest.mark.asyncio
    async def test_429_sets_backoff_correctly(self):
        """handle_429 sets backoff immediately (before the sleep)."""
        task = asyncio.create_task(self.rl.handle_429(123, retry_after=0))
        await asyncio.sleep(0.01)  # let the task start and set backoff
        assert 123 in self.rl._global_backoff
        assert self.rl._global_backoff[123] > time.time() + 1.5  # min 2s
        task.cancel()  # cancel the sleep
