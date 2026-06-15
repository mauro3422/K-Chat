"""Stream parser — converts tagged adapter strings into phase-tracked events.

Tags follow the convention::

    ``__reasoning__:<text>``  — reasoning (thinking) tokens
    ``__content__:<text>``    — visible content tokens
    ``__tool__:<name>``       — tool call (name only, no content)
    ``__error__:<message>``   — error message

The parser tracks *phases*: each time the event type switches, it
increments the appropriate phase counter so the renderer knows whether
to create a new message or edit an existing one.

Phase rules (mirror the WebUI's phase-index logic):

- reasoning → reasoning    : same phase, edit in place
- reasoning → content      : new content phase, create new message
- content  → content       : same phase, edit in place
- content  → reasoning     : new reasoning phase, create new message
- tool                     : always terminal for current phases
- anything → error         : terminal, stop
"""

from __future__ import annotations

from channels.telegram.protocols import (
    ContentEvent,
    ErrorEvent,
    ReasoningEvent,
    StreamEvent,
    ToolCallEvent,
)


class StreamParser:
    """Converts tagged strings into typed events with phase tracking.

    Usage::

        parser = StreamParser()
        for event in parser.feed("__reasoning__:Let me think"):
            ...  # ReasoningEvent(text="Let me think", is_new_phase=True)
        for event in parser.feed("__reasoning__: more"):
            ...  # ReasoningEvent(text=" more", is_new_phase=False)
    """

    TAG_REASONING = "__reasoning__:"
    TAG_CONTENT = "__content__:"
    TAG_TOOL = "__tool__:"
    TAG_ERROR = "__error__:"

    def __init__(self) -> None:
        # Phase counters
        self._reasoning_phase = 0
        self._content_phase = 0
        self._last_type: str | None = None  # "reasoning" | "content" | "tool" | "error"
        self._finished = False

    @property
    def reasoning_phase(self) -> int:
        return self._reasoning_phase

    @property
    def content_phase(self) -> int:
        return self._content_phase

    # ── Public API ──────────────────────────────────────────────────────

    def feed(self, tagged: str) -> list[StreamEvent]:
        """Process one tagged string. Returns zero or more StreamEvents."""
        if self._finished:
            return []

        tag, data = self._parse(tagged)
        if tag is None:
            return []

        if tag == "error":
            self._finished = True
            return [ErrorEvent(message=data)]

        if tag == "tool":
            self._on_transition("tool")
            # data format: "tool_id:name:status"
            parts = data.split(":", 2)
            tool_id = parts[0] if len(parts) >= 1 else ""
            name = parts[1] if len(parts) >= 2 else data
            status = parts[2] if len(parts) >= 3 else "calling"
            return [ToolCallEvent(name=name, status=status, tool_id=tool_id)]

        if tag == "reasoning":
            events: list[StreamEvent] = []
            is_new = self._on_transition("reasoning")
            events.append(ReasoningEvent(text=data, is_new_phase=is_new))
            return events

        if tag == "content":
            is_new = self._on_transition("content")
            return [ContentEvent(text=data, is_new_phase=is_new)]

        return []

    def flush(self) -> list[StreamEvent]:
        """Flush any remaining buffers. Currently a no-op (we flush inline).

        Returns an empty list. Subclasses with buffering override this.
        """
        return []

    # ── Internals ───────────────────────────────────────────────────────

    def _parse(self, tagged: str) -> tuple[str | None, str]:
        """Extract tag and data from a tagged string.

        Returns ``(tag, data)`` or ``(None, "")`` if no tag found.
        """
        if tagged.startswith(self.TAG_REASONING):
            return ("reasoning", tagged[len(self.TAG_REASONING):])
        if tagged.startswith(self.TAG_CONTENT):
            return ("content", tagged[len(self.TAG_CONTENT):])
        if tagged.startswith(self.TAG_TOOL):
            return ("tool", tagged[len(self.TAG_TOOL):])
        if tagged.startswith(self.TAG_ERROR):
            return ("error", tagged[len(self.TAG_ERROR):])
        return (None, "")

    def _on_transition(self, new_type: str) -> bool:
        """Handle a transition between event types.

        Returns ``True`` if this is a new phase (caller should create a
        new message), ``False`` if same phase (caller should edit).
        """
        if new_type == "tool":
            # Tool calls reset both reasoning and content phases.
            # Setting _last_type = None means the NEXT event (reasoning
            # or content) will be treated as first-of-phase (→ new msg).
            self._reasoning_phase += 1
            self._content_phase += 1
            self._last_type = None
            return True  # tool always creates a new message

        if new_type == "reasoning":
            if self._last_type == "content":
                # Transition content → reasoning: new reasoning phase
                self._reasoning_phase += 1
                self._last_type = "reasoning"
                return True  # new phase → new message
            is_first = self._last_type is None
            self._last_type = "reasoning"
            return is_first  # only new if first event ever

        if new_type == "content":
            if self._last_type == "reasoning":
                # Transition reasoning → content: new content phase
                self._content_phase += 1
                self._last_type = "content"
                return True  # new phase → new message
            is_first = self._last_type is None
            self._last_type = "content"
            return is_first

        return False
