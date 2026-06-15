"""Tests for Telegram handlers — command priority & message dispatch."""

import pytest

from channels.telegram.handlers import dispatch


class TestHandlers:
    """Tests for handler dispatch — commands MUST be parsed before text."""

    def test_start_command(self):
        """/start is detected."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 10,
                "text": "/start",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is not None
        text, info = result
        assert text == "/start"
        assert info["is_command"] is True
        assert info["chat_id"] == 123

    def test_help_command(self):
        """/help is detected."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 11,
                "text": "/help",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is not None
        assert result[0] == "/help"

    def test_new_command(self):
        """/new is detected."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 12,
                "text": "/new",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is not None
        assert result[0] == "/new"

    def test_reset_command(self):
        """/reset is detected."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 13,
                "text": "/reset",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is not None
        assert result[0] == "/reset"

    def test_commands_case_insensitive(self):
        """Commands are case-insensitive (lowered in handler)."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 14,
                "text": "/START",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is not None
        assert result[0] == "/start"

    def test_regular_text(self):
        """Plain text is handled by the catch-all text handler."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 15,
                "text": "Hello, how are you?",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is not None
        text, info = result
        assert text == "Hello, how are you?"
        assert info["is_command"] is False

    def test_voice_message(self):
        """Voice messages produce the __voice__ marker."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 16,
                "voice": {"file_id": "abc123", "duration": 5},
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is not None
        assert result[0].startswith("__voice__:")

    def test_edited_message(self):
        """Edited messages are handled (fallback to text handler)."""
        result = dispatch({
            "update_id": 1,
            "edited_message": {
                "message_id": 17,
                "text": "Fixed typo",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000001,
            },
        })
        assert result is not None
        assert result[0] == "Fixed typo"

    def test_no_message(self):
        """Updates without a message return None."""
        result = dispatch({"update_id": 1})
        assert result is None

    def test_empty_text(self):
        """Messages with empty text return None."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 18,
                "text": "",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        assert result is None

    def test_command_not_text(self):
        """Commands take priority — /start is NOT treated as text."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 19,
                "text": "/start",
                "chat": {"id": 123},
                "from": {"id": 456},
                "date": 1000000,
            },
        })
        # Should be /start, not plain text
        assert result is not None
        text, info = result
        assert text == "/start"
        assert info["is_command"] is True

    def test_metadata_in_message_info(self):
        """Message info dict includes correct metadata."""
        result = dispatch({
            "update_id": 1,
            "message": {
                "message_id": 20,
                "text": "test",
                "chat": {"id": 789},
                "from": {"id": 321},
                "date": 9999999,
            },
        })
        assert result is not None
        _, info = result
        assert info["chat_id"] == 789
        assert info["message_id"] == 20
        assert info["from_user"] == 321
        assert info["date"] == 9999999
        assert info["is_command"] is False
