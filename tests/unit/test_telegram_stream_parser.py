"""Tests for the Telegram stream parser — phase tracking & event types."""

import pytest

from channels.telegram.protocols import (
    ContentEvent,
    ErrorEvent,
    ReasoningEvent,
    ToolCallEvent,
)
from channels.telegram.stream_parser import StreamParser


class TestStreamParser:
    """Unit tests for StreamParser — pure logic, no IO."""

    def test_reasoning_first_event(self):
        """First reasoning event creates new phase."""
        p = StreamParser()
        events = p.feed("__reasoning__:Let me think")
        assert len(events) == 1
        assert isinstance(events[0], ReasoningEvent)
        assert events[0].text == "Let me think"
        assert events[0].is_new_phase is True

    def test_reasoning_continuation(self):
        """Same-phase reasoning edits in place."""
        p = StreamParser()
        p.feed("__reasoning__:Let me")
        events = p.feed("__reasoning__: think")
        assert len(events) == 1
        assert isinstance(events[0], ReasoningEvent)
        assert events[0].text == " think"
        assert events[0].is_new_phase is False

    def test_content_first_event(self):
        """First content event creates new phase."""
        p = StreamParser()
        events = p.feed("__content__:Hello")
        assert len(events) == 1
        assert isinstance(events[0], ContentEvent)
        assert events[0].text == "Hello"
        assert events[0].is_new_phase is True

    def test_content_continuation(self):
        """Same-phase content edits in place."""
        p = StreamParser()
        p.feed("__content__:Hello")
        events = p.feed("__content__: world")
        assert events[0].is_new_phase is False
        assert events[0].text == " world"

    def test_reasoning_to_content_creates_new_content_phase(self):
        """Transition reasoning→content creates new content phase."""
        p = StreamParser()
        p.feed("__reasoning__:Pienso")
        events = p.feed("__content__:Responde")
        assert len(events) == 1
        assert isinstance(events[0], ContentEvent)
        assert events[0].is_new_phase is True
        assert p.content_phase == 1  # first content phase

    def test_content_to_reasoning_creates_new_reasoning_phase(self):
        """Transition content→reasoning creates NEW reasoning message.

        This is the CRITICAL bug fix: new reasoning after content must NOT
        edit the old reasoning message.
        """
        p = StreamParser()
        p.feed("__reasoning__:Pienso")  # reasoning_phase=0
        p.feed("__content__:Responde")   # content_phase=1
        events = p.feed("__reasoning__:Pienso de nuevo")

        assert len(events) == 1
        assert isinstance(events[0], ReasoningEvent)
        assert events[0].is_new_phase is True  # NEW phase → new message!
        assert p.reasoning_phase == 1  # second reasoning phase
        # First reasoning was phase 0, this new one is phase 1

    def test_multiple_reasoning_content_cycles(self):
        """Multiple reasoning→content→reasoning cycles increment phases."""
        p = StreamParser()

        # Cycle 1
        p.feed("__reasoning__:R1")
        assert p.reasoning_phase == 0
        p.feed("__content__:C1")
        assert p.content_phase == 1

        # Cycle 2
        p.feed("__reasoning__:R2")
        assert p.reasoning_phase == 1
        p.feed("__content__:C2")
        assert p.content_phase == 2

        # Cycle 3
        p.feed("__reasoning__:R3")
        assert p.reasoning_phase == 2
        p.feed("__content__:C3")
        assert p.content_phase == 3

    def test_tool_call(self):
        """Tool call creates ToolCallEvent and resets phase tracking."""
        p = StreamParser()
        events = p.feed("__tool__:web_search")
        assert len(events) == 1
        assert isinstance(events[0], ToolCallEvent)
        assert events[0].name == "web_search"

    def test_tool_between_reasoning_and_content(self):
        """Tool call is INLINE — next reasoning continues same phase.

        Unlike the web UI where tools create a new turn boundary, Telegram
        renders tools inline in the same reasoning message to avoid visual
        fragmentation. Reasoning after a tool call APPENDS to the existing
        message, it does NOT create a new one.
        """
        p = StreamParser()
        p.feed("__reasoning__:Pienso")  # reasoning_phase=0, new_phase=True
        p.feed("__tool__:search")        # inline tool, _last_type="tool"

        # Next reasoning is SAME phase (tool was inline)
        events = p.feed("__reasoning__:Pienso otra vez")
        assert events[0].is_new_phase is False  # same phase!
        assert p.reasoning_phase == 0  # no increment

    def test_error_event(self):
        """Error creates ErrorEvent and marks stream as finished."""
        p = StreamParser()
        events = p.feed("__error__:Something broke")
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert events[0].message == "Something broke"

        # After error, no more events
        assert p.feed("__reasoning__:more") == []

    def test_unknown_tag(self):
        """Unknown tags return empty list."""
        p = StreamParser()
        assert p.feed("__unknown__:stuff") == []
        assert p.feed("plain text") == []

    def test_none_chunk(self):
        """None chunks return empty list."""
        p = StreamParser()
        assert p.feed("") == []

    def test_flush_noop(self):
        """Flush returns empty (no buffering in basic parser)."""
        p = StreamParser()
        p.feed("__reasoning__:test")
        assert p.flush() == []

    def test_reasoning_phase_property(self):
        """reasoning_phase and content_phase properties reflect state."""
        p = StreamParser()
        assert p.reasoning_phase == 0
        assert p.content_phase == 0
        p.feed("__reasoning__:R")
        assert p.reasoning_phase == 0
        p.feed("__content__:C")
        assert p.content_phase == 1
