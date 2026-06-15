"""Tests for the Telegram error handler — error classification & recovery."""

import pytest
import httpx
from unittest.mock import Mock

from channels.telegram.error_handler import TelegramErrorHandler
from channels.telegram.protocols import ErrorHandlerProtocol


class TestTelegramErrorHandler:
    """Unit tests for TelegramErrorHandler — pure classification logic."""

    def setup_method(self):
        self.eh = TelegramErrorHandler()

    @pytest.mark.asyncio
    async def test_429_rate_limit(self):
        """429 returns retry with wait_seconds."""
        resp = Mock()
        resp.status_code = 429
        resp.text = '{"ok":false,"parameters":{"retry_after":5}}'
        resp.json.return_value = {"ok": False, "parameters": {"retry_after": 5}}
        error = httpx.HTTPStatusError("rate limited", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is True
        assert action.wait_seconds >= 5
        assert action.abort is False

    @pytest.mark.asyncio
    async def test_400_message_not_modified(self):
        """400 'message not modified' returns benign (no retry, no abort)."""
        resp = Mock()
        resp.status_code = 400
        resp.text = "Bad Request: message is not modified"
        error = httpx.HTTPStatusError("not modified", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is False
        assert action.abort is False

    @pytest.mark.asyncio
    async def test_400_too_long(self):
        """400 'too long' returns fallback text."""
        resp = Mock()
        resp.status_code = 400
        resp.text = "Bad Request: message is too long"
        error = httpx.HTTPStatusError("too long", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is False
        assert action.abort is False
        assert action.fallback_text is not None
        assert "truncated" in (action.fallback_text or "")

    @pytest.mark.asyncio
    async def test_400_cant_parse(self):
        """400 'can't parse entities' retries as plain text."""
        resp = Mock()
        resp.status_code = 400
        resp.text = "Bad Request: can't parse entities"
        error = httpx.HTTPStatusError("can't parse", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is True

    @pytest.mark.asyncio
    async def test_403_forbidden(self):
        """403 returns abort."""
        resp = Mock()
        resp.status_code = 403
        resp.text = "Forbidden: bot was blocked by the user"
        error = httpx.HTTPStatusError("forbidden", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.abort is True
        assert action.retry is False

    @pytest.mark.asyncio
    async def test_404_not_found(self):
        """404 returns benign (no retry, no abort)."""
        resp = Mock()
        resp.status_code = 404
        resp.text = "Not Found"
        error = httpx.HTTPStatusError("not found", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is False
        assert action.abort is False

    @pytest.mark.asyncio
    async def test_409_conflict(self):
        """409 returns retry."""
        resp = Mock()
        resp.status_code = 409
        resp.text = "Conflict: webhook is set"
        error = httpx.HTTPStatusError("conflict", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is True

    @pytest.mark.asyncio
    async def test_401_unauthorized_retry(self):
        """401 returns retry (could be transient)."""
        resp = Mock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        error = httpx.HTTPStatusError("unauthorized", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is True

    @pytest.mark.asyncio
    async def test_500_server_error_retry(self):
        """500 returns retry."""
        resp = Mock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        error = httpx.HTTPStatusError("server error", request=Mock(), response=resp)

        action = await self.eh.classify(error)
        assert action.retry is True

    @pytest.mark.asyncio
    async def test_timeout_retry(self):
        """Timeout returns retry."""
        error = httpx.TimeoutException("Connection timed out")
        action = await self.eh.classify(error)
        assert action.retry is True
        assert action.wait_seconds > 0

    @pytest.mark.asyncio
    async def test_network_error_retry(self):
        """Network error returns retry."""
        error = httpx.NetworkError("Connection refused")
        action = await self.eh.classify(error)
        assert action.retry is True

    @pytest.mark.asyncio
    async def test_unknown_error_abort(self):
        """Unknown error type returns abort."""
        error = ValueError("Something unexpected")
        action = await self.eh.classify(error)
        assert action.abort is True
        assert action.retry is False
