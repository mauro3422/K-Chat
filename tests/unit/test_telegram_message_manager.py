"""Tests for the Telegram message manager — phase & message ID tracking."""

import pytest

from channels.telegram.message_manager import MessageManager


class TestMessageManager:
    """Unit tests for MessageManager — pure state tracking."""

    def setup_method(self):
        self.mm = MessageManager()

    def test_get_set_msg_id(self):
        """Setting and getting a message ID works."""
        self.mm.set_msg_id(123, "reasoning", 0, 1001)
        assert self.mm.get_msg_id(123, "reasoning", 0) == 1001

    def test_get_nonexistent_msg_id(self):
        """Getting a non-existent phase returns None."""
        assert self.mm.get_msg_id(999, "reasoning", 0) is None

    def test_has_phase_true(self):
        """has_phase returns True for stored phases."""
        self.mm.set_msg_id(123, "content", 0, 2001)
        assert self.mm.has_phase(123, "content", 0) is True

    def test_has_phase_false(self):
        """has_phase returns False for unstored phases."""
        assert self.mm.has_phase(456, "reasoning", 5) is False

    def test_multiple_chats_isolated(self):
        """Different chat IDs have isolated state."""
        self.mm.set_msg_id(111, "reasoning", 0, 100)
        self.mm.set_msg_id(222, "reasoning", 0, 200)
        assert self.mm.get_msg_id(111, "reasoning", 0) == 100
        assert self.mm.get_msg_id(222, "reasoning", 0) == 200

    def test_multiple_phases_same_chat(self):
        """Multiple phases for the same chat are tracked independently."""
        self.mm.set_msg_id(123, "reasoning", 0, 1001)
        self.mm.set_msg_id(123, "content", 0, 2001)
        self.mm.set_msg_id(123, "reasoning", 1, 1002)
        self.mm.set_msg_id(123, "content", 1, 2002)

        assert self.mm.get_msg_id(123, "reasoning", 0) == 1001
        assert self.mm.get_msg_id(123, "content", 0) == 2001
        assert self.mm.get_msg_id(123, "reasoning", 1) == 1002
        assert self.mm.get_msg_id(123, "content", 1) == 2002

    def test_reset_phases_clears_reasoning_and_content(self):
        """reset_phases clears reasoning and content phases but not tools."""
        self.mm.set_msg_id(123, "reasoning", 0, 1001)
        self.mm.set_msg_id(123, "content", 0, 2001)
        self.mm.set_tool_msg_id(123, "call_x", 3001)

        self.mm.reset_phases(123)

        # Reasoning and content should be cleared
        assert self.mm.get_msg_id(123, "reasoning", 0) is None
        assert self.mm.get_msg_id(123, "content", 0) is None
        # Tools should remain
        assert self.mm.get_tool_msg_id(123, "call_x") == 3001

    def test_reset_phases_then_new_phase(self):
        """After reset_phases, new phases create new messages (not found)."""
        self.mm.set_msg_id(123, "reasoning", 0, 1001)
        self.mm.reset_phases(123)
        # New reasoning should not find old msg_id
        assert self.mm.get_msg_id(123, "reasoning", 0) is None

    def test_tool_messages(self):
        """Tool message IDs are tracked separately."""
        self.mm.set_tool_msg_id(123, "call_abc", 4001)
        assert self.mm.get_tool_msg_id(123, "call_abc") == 4001
        assert self.mm.get_tool_msg_id(123, "call_xyz") is None

    def test_cleanup_removes_all(self):
        """cleanup removes all state for a chat."""
        self.mm.set_msg_id(123, "reasoning", 0, 1001)
        self.mm.set_tool_msg_id(123, "call_x", 3001)
        self.mm.cleanup(123)
        assert self.mm.get_msg_id(123, "reasoning", 0) is None
        assert self.mm.get_tool_msg_id(123, "call_x") is None
