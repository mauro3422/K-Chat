"""Smoke tests for vectorize_sessions module — pure functions only."""

from __future__ import annotations

from src.memory.noise_filter import is_noise
from src.memory.vectorize_sessions import _normalize_for_dedup, group_into_exchanges


class TestGroupIntoExchanges:
    def test_empty_list_returns_empty(self):
        assert group_into_exchanges([]) == []

    def test_single_user_message_returns_one_exchange(self):
        messages = [{"role": "user", "content": "hello"}]
        result = group_into_exchanges(messages)
        assert len(result) == 1
        assert "User: hello" in result[0]["text"]
        assert "Assistant: _pending_" in result[0]["text"]

    def test_user_assistant_pair_returns_one_exchange(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = group_into_exchanges(messages)
        assert len(result) == 1
        assert "User: hello" in result[0]["text"]
        assert "Assistant: hi there" in result[0]["text"]

    def test_user_tool_assistant_returns_one_exchange(self):
        messages = [
            {"role": "user", "content": "search for x"},
            {"role": "tool", "content": "result 1\nresult 2"},
            {"role": "assistant", "content": "here are the results"},
        ]
        result = group_into_exchanges(messages)
        assert len(result) == 1
        assert "Assistant: here are the results" in result[0]["text"]

    def test_multiple_exchanges_returns_correct_count(self):
        messages = [
            {"role": "user", "content": "first q"},
            {"role": "assistant", "content": "first a"},
            {"role": "user", "content": "second q"},
            {"role": "assistant", "content": "second a"},
            {"role": "user", "content": "third q"},
        ]
        result = group_into_exchanges(messages)
        assert len(result) == 3


class TestNormalizeForDedup:
    def test_lowercases(self):
        assert _normalize_for_dedup("HELLO WORLD") == "hello world"

    def test_removes_code_blocks(self):
        text = "some text ```python\nprint('hello')\n``` more text"
        result = _normalize_for_dedup(text)
        assert "print" not in result
        assert "some text" in result
        assert "more text" in result

    def test_collapses_whitespace(self):
        text = "hello    world\n\n  foo"
        result = _normalize_for_dedup(text)
        assert result == "hello world foo"


class TestIsNoise:
    def test_short_text_returns_true(self):
        noisy, reason = is_noise("hi", role="user")
        assert noisy is True

    def test_meaningful_text_returns_false(self):
        text = (
            "This is a meaningful query about how to implement a sorting "
            "algorithm in Python. I need to understand the complexity analysis."
        )
        noisy, reason = is_noise(text, role="user")
        assert noisy is False
