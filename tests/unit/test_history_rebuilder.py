"""Tests for history_rebuilder.py"""
from unittest.mock import MagicMock, patch
import pytest

from src.core.history_rebuilder import rebuild_history

SYSTEM_PROMPT = {"role": "system", "content": "You are Kairos..."}


def test_accepts_injected_messages_repo():
    repo = MagicMock()
    repo.get_session_messages.return_value = []
    with patch("src.core.history_rebuilder.build_system_prompt", return_value=SYSTEM_PROMPT):
        result = rebuild_history("test-session", "test-model", messages_repo=repo)
    repo.get_session_messages.assert_called_once_with("test-session")
    assert result[0] == SYSTEM_PROMPT


def test_returns_system_prompt_for_empty_history():
    repo = MagicMock()
    repo.get_session_messages.return_value = []
    with patch("src.core.history_rebuilder.build_system_prompt", return_value=SYSTEM_PROMPT):
        with patch("src.core.history_rebuilder._parse_rows", return_value=[]):
            with patch("src.core.history_rebuilder._sanitize_messages", return_value=[]):
                result = rebuild_history("empty", "gpt-4", messages_repo=repo)
    assert len(result) == 1
    assert result[0] == SYSTEM_PROMPT


def test_formats_messages_through_pipeline():
    repo = MagicMock()
    repo.get_session_messages.return_value = [{"role": "user", "content": "Hello"}]
    parsed = [{"role": "user", "content": "[2025-01-01 12:00:00] Hello"}]
    sanitized = [{"role": "user", "content": "[2025-01-01 12:00:00] Hello"}]

    with patch("src.core.history_rebuilder.build_system_prompt", return_value=SYSTEM_PROMPT):
        with patch("src.core.history_rebuilder._parse_rows", return_value=parsed):
            with patch("src.core.history_rebuilder._sanitize_messages", return_value=sanitized):
                result = rebuild_history("s1", "m1", messages_repo=repo)

    assert len(result) == 2
    assert result[0] == SYSTEM_PROMPT
    assert result[1] == sanitized[0]


def test_fallback_get_repos():
    with patch("src.core.history_rebuilder.build_system_prompt", return_value=SYSTEM_PROMPT):
        with pytest.raises(ValueError):
            rebuild_history("test", "m", messages_repo=None)
