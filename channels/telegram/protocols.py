"""Protocols for the Telegram channel — Lego building blocks.

Each protocol defines a single responsibility. Concrete implementations
can be swapped, mocked, or tested independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ─── Event types from stream parser → renderer ──────────────────────────

@dataclass
class ReasoningEvent:
    """Reasoning (thinking) token from the model."""
    text: str
    is_new_phase: bool = False


@dataclass
class ContentEvent:
    """Content (visible text) token from the model."""
    text: str
    is_new_phase: bool = False


@dataclass
class ToolCallEvent:
    """Tool call notification."""
    name: str
    status: str = "calling"  # calling | ok | error
    tool_id: str = ""


@dataclass
class ErrorEvent:
    """Error during processing."""
    message: str


StreamEvent = ReasoningEvent | ContentEvent | ToolCallEvent | ErrorEvent


# ─── Render actions (what the renderer tells the API layer) ─────────────

@dataclass
class SendAction:
    """Send a new message."""
    chat_id: int
    text: str
    parse_mode: str = ""


@dataclass
class EditAction:
    """Edit an existing message."""
    chat_id: int
    message_id: int
    text: str
    parse_mode: str = ""


@dataclass
class SendTypingAction:
    """Send chat action (typing indicator)."""
    chat_id: int
    action: str = "typing"


RenderAction = SendAction | EditAction | SendTypingAction


# ─── Protocols ──────────────────────────────────────────────────────────

@runtime_checkable
class TelegramAPIClientProtocol(Protocol):
    """Low-level Telegram Bot API calls.

    Implementations wrap httpx.AsyncClient calls to api.telegram.org.
    """

    async def send_message(
        self, chat_id: int, text: str, parse_mode: str = "",
    ) -> int | None:
        """Send a new message. Returns ``message_id`` or ``None`` on failure."""
        ...

    async def edit_message(
        self, chat_id: int, message_id: int, text: str, parse_mode: str = "",
    ) -> bool:
        """Edit an existing message. Returns ``True`` on success."""
        ...

    async def send_action(self, chat_id: int, action: str = "typing") -> None:
        """Send a chat action (e.g. typing indicator)."""
        ...


@runtime_checkable
class MessageManagerProtocol(Protocol):
    """Tracks message IDs per conversation phase per chat.

    Phases are numbered sequentially. When a phase resets (e.g. after a
    tool call), the old phase number is archived and a new one starts.
    """

    async def get_or_create_message(
        self,
        chat_id: int,
        phase_type: str,  # "reasoning" | "content"
        phase_index: int,
        text: str,
        parse_mode: str = "",
    ) -> int:
        """Get the message_id for a phase, creating a new message if needed.

        Returns the message_id (existing or newly created).
        """
        ...

    async def edit_phase_message(
        self,
        chat_id: int,
        phase_type: str,
        phase_index: int,
        text: str,
        parse_mode: str = "",
    ) -> bool:
        """Edit the message for a specific phase. Returns True on success."""
        ...

    async def reset_phases(self, chat_id: int) -> None:
        """Reset all phases (called after tool call)."""
        ...

    async def cleanup(self, chat_id: int) -> None:
        """Clean up state for a chat (on stream end)."""
        ...


@runtime_checkable
class RateLimiterProtocol(Protocol):
    """Throttles edits to respect Telegram's per-message rate limits."""

    async def wait_if_needed(self, chat_id: int, message_id: int) -> None:
        """Wait if we're about to hit the rate limit for this message."""
        ...

    async def record_edit(self, chat_id: int, message_id: int) -> None:
        """Record that an edit was made for rate limit tracking."""
        ...

    async def handle_429(self, chat_id: int, retry_after: int) -> None:
        """Handle a 429 Too Many Requests response."""
        ...


@runtime_checkable
class CharSplitterProtocol(Protocol):
    """Splits long text into Telegram-safe chunks."""

    MAX_CHARS: int = 4000  # safety margin below 4096

    def split(self, text: str, max_chars: int | None = None) -> list[str]:
        """Split text at word boundaries into chunks <= max_chars.

        Returns a list of chunks. Single chunk if text fits.
        """
        ...


@dataclass
class RecoveryAction:
    """Action to take after classifying an error."""
    retry: bool = False
    abort: bool = False
    fallback_text: str | None = None
    wait_seconds: float = 0.0


@runtime_checkable
class ErrorHandlerProtocol(Protocol):
    """Classifies Telegram API errors and returns recovery actions."""

    async def classify(
        self, error: Exception, context: dict | None = None,
    ) -> RecoveryAction:
        """Classify an error and decide what to do next."""
        ...


@runtime_checkable
class StreamParserProtocol(Protocol):
    """Converts tagged event strings from the adapter into typed events.

    Also tracks phase transitions so the renderer knows when to create
    new messages vs edit existing ones.
    """

    def feed(self, tagged: str) -> list[StreamEvent]:
        """Process one tagged string. Returns zero or more StreamEvents."""
        ...

    def flush(self) -> list[StreamEvent]:
        """Flush any remaining buffers. Returns final events."""
        ...

    @property
    def reasoning_phase(self) -> int:
        """Current reasoning phase index."""
        ...

    @property
    def content_phase(self) -> int:
        """Current content phase index."""
        ...


@runtime_checkable
class TelegramRendererProtocol(Protocol):
    """Orchestrates rendering of stream events to Telegram messages.

    Uses the lower-level components (APIClient, MessageManager, etc.)
    to produce the right sequence of sends and edits.
    """

    async def render_stream(
        self,
        chat_id: int,
        process_fn,  # async generator yielding tagged strings
    ) -> None:
        """Render an entire message stream to Telegram messages.

        Args:
            chat_id: Telegram chat ID.
            process_fn: async generator that yields tagged strings
                       (``__reasoning__:``, ``__content__:``, etc.)
        """
        ...
