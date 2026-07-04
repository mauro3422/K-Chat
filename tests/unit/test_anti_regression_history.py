"""Anti-regression tests for history rebuild, message persistence, and error classifier.

Covers the fixes applied to prevent:
- Tool messages appearing without their assistant tool_calls (DeepSeek 400)
- Empty assistant messages polluting history
- Empty tool_calls list [] sent to LLM
- _parse_duration_value missing return statement
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock


# ── History parser tests ─────────────────────────────────────────

class TestHistoryParser:
    """Verify _sanitize_messages handles tool pairing correctly."""

    def test_tool_pairing_with_empty_assistant_between(self):
        """Empty assistant between tool_calls and tool responses should be skipped."""
        from src._types import HistoryMessage
        from src.core.history_parser import _sanitize_messages

        msgs = [
            HistoryMessage(role="user", content="search", created_at=""),
            HistoryMessage(role="assistant", content=None, tool_calls=[
                {"id": "call_1", "function": {"name": "test", "arguments": "{}"}}
            ], created_at=""),
            # Empty assistant interleaved — should be SKIPPED, not break pairing
            HistoryMessage(role="assistant", content="", tool_calls=None, created_at=""),
            HistoryMessage(role="tool", content="result", tool_call_id="call_1", created_at=""),
        ]
        result = _sanitize_messages(msgs)
        # Should have: user, assistant(with tool_calls), tool
        assert len(result) == 3
        assert result[0].role == "user"
        assert result[1].role == "assistant"
        assert result[1].tool_calls is not None
        assert result[2].role == "tool"

    def test_tool_pairing_normal(self):
        """Normal tool pairing without interleaved messages."""
        from src._types import HistoryMessage
        from src.core.history_parser import _sanitize_messages

        msgs = [
            HistoryMessage(role="user", content="search", created_at=""),
            HistoryMessage(role="assistant", content=None, tool_calls=[
                {"id": "call_1", "function": {"name": "test", "arguments": "{}"}}
            ], created_at=""),
            HistoryMessage(role="tool", content="result", tool_call_id="call_1", created_at=""),
            HistoryMessage(role="assistant", content="answer", tool_calls=None, created_at=""),
        ]
        result = _sanitize_messages(msgs)
        assert len(result) == 4

    def test_orphan_tool_messages_removed(self):
        """Tool messages without preceding assistant tool_calls should be removed."""
        from src._types import HistoryMessage
        from src.core.history_parser import _sanitize_messages

        msgs = [
            HistoryMessage(role="user", content="hi", created_at=""),
            HistoryMessage(role="tool", content="orphan", tool_call_id="call_1", created_at=""),
            HistoryMessage(role="user", content="next", created_at=""),
        ]
        result = _sanitize_messages(msgs)
        # Orphan tool message should be stripped
        roles = [m.role for m in result]
        assert "tool" not in roles

    def test_empty_assistant_kept_in_default_case(self):
        """Empty assistant messages should be kept (existing behavior)."""
        from src._types import HistoryMessage
        from src.core.history_parser import _sanitize_messages

        msgs = [
            HistoryMessage(role="user", content="hi", created_at=""),
            HistoryMessage(role="assistant", content="", tool_calls=None, created_at=""),
            HistoryMessage(role="user", content="next", created_at=""),
        ]
        result = _sanitize_messages(msgs)
        roles = [m.role for m in result]
        assert roles == ["user", "assistant", "user"]  # empty assistant kept


# ── as_llm_message tests ─────────────────────────────────────────

class TestAsLlmMessage:
    """Verify as_llm_message doesn't include empty tool_calls."""

    def test_empty_tool_calls_not_included(self):
        """tool_calls=[] should NOT appear in the output dict."""
        from src._types import HistoryMessage
        msg = HistoryMessage(role="assistant", content="hi", tool_calls=[], created_at="")
        result = msg.as_llm_message()
        assert "tool_calls" not in result

    def test_null_tool_calls_not_included(self):
        """tool_calls=None should NOT appear in the output dict."""
        from src._types import HistoryMessage
        msg = HistoryMessage(role="assistant", content="hi", tool_calls=None, created_at="")
        result = msg.as_llm_message()
        assert "tool_calls" not in result

    def test_valid_tool_calls_included(self):
        """tool_calls with content SHOULD appear."""
        from src._types import HistoryMessage
        msg = HistoryMessage(role="assistant", content=None, tool_calls=[
            {"id": "call_1", "function": {"name": "test", "arguments": "{}"}}
        ], created_at="")
        result = msg.as_llm_message()
        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1


# ── Message persister tests ──────────────────────────────────────

class TestMessagePersister:
    """Verify empty assistant messages are not persisted."""

    @pytest.mark.asyncio
    async def test_empty_message_not_saved(self):
        """save_assistant_message with empty content+reasoning should return early."""
        from web.services.message_persister import save_assistant_message
        from src.api.repos import DebugInfo

        deps = MagicMock()
        deps.save_message_fn = AsyncMock()
        debug_info = DebugInfo(model="test", reasoning="", system_prompt="",
                               tool_calls=[], history_before=[], auto_memories="")

        await save_assistant_message(
            session_id="test", full_content="", full_reasoning="",
            phases_output=[], debug_info=debug_info, model="test",
            deps=deps,
        )
        # Should NOT call save_message_fn because content is empty
        deps.save_message_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_content_only_saved(self):
        """Message with content but no reasoning should be saved."""
        from web.services.message_persister import save_assistant_message
        from src.api.repos import DebugInfo

        deps = MagicMock()
        deps.save_message_fn = AsyncMock()
        deps.message_record_cls = MagicMock()
        deps.save_debug_fn = MagicMock()
        debug_info = DebugInfo(model="test", reasoning="", system_prompt="",
                               tool_calls=[], history_before=[], auto_memories="")

        await save_assistant_message(
            session_id="test", full_content="hello world", full_reasoning="",
            phases_output=[], debug_info=debug_info, model="test",
            deps=deps,
        )
        deps.save_message_fn.assert_called_once()


# ── Error classifier regression ──────────────────────────────────

class TestParseDurationValue:
    """Verify _parse_duration_value returns correct values."""

    def test_simple_seconds(self):
        from web.services.stream_error_classifier import _parse_duration_value
        assert _parse_duration_value("60") == 60

    def test_minutes_seconds_format(self):
        from web.services.stream_error_classifier import _parse_duration_value
        result = _parse_duration_value("5m30s")
        assert result is not None, "Should parse '5m30s' format"
        assert result == 330  # 5*60 + 30

    def test_minutes_only(self):
        from web.services.stream_error_classifier import _parse_duration_value
        result = _parse_duration_value("10m")
        assert result == 600

    def test_seconds_only_format(self):
        from web.services.stream_error_classifier import _parse_duration_value
        result = _parse_duration_value("45s")
        assert result == 45

    def test_empty_returns_none(self):
        from web.services.stream_error_classifier import _parse_duration_value
        assert _parse_duration_value("") is None
        assert _parse_duration_value(None) is None
