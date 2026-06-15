"""Message manager — tracks Telegram message IDs per conversation phase.

Each chat has a state dict that maps phase keys to message IDs:

.. code-block:: python

    {
        "reasoning:0": 123,   # first reasoning block
        "content:0": 124,     # first content block  
        "reasoning:1": 125,   # second reasoning block (after tool or content→reasoning)
        "content:1": 126,     # second content block
        "tool:call_X": 127,   # individual tool call message (static)
    }

Phases are *immutable* once created — a phase key always points to the
same message ID. When a phase transitions (reasoning→content→reasoning),
new phases are created with incremented indices.
"""

from __future__ import annotations

from collections import defaultdict

from channels.telegram.protocols import TelegramAPIClientProtocol


class MessageManager:
    """Tracks message IDs per (chat, phase_type, phase_index).

    This is a pure state manager — it does NOT make API calls. The
    caller (TelegramRenderer) creates messages via the API client
    and tells the manager to store the resulting IDs.
    """

    def __init__(self) -> None:
        # {chat_id: {"reasoning:0": msg_id, "content:2": msg_id, ...}}
        self._state: dict[int, dict[str, int]] = defaultdict(dict)
        # {chat_id: {"tool:call_X": msg_id}}
        self._tool_msgs: dict[int, dict[str, int]] = defaultdict(dict)

    # ── Phase tracking ──────────────────────────────────────────────────

    def _phase_key(self, phase_type: str, phase_index: int) -> str:
        return f"{phase_type}:{phase_index}"

    def get_msg_id(self, chat_id: int, phase_type: str, phase_index: int) -> int | None:
        """Get the message ID for a specific phase, or None."""
        key = self._phase_key(phase_type, phase_index)
        return self._state.get(chat_id, {}).get(key)

    def set_msg_id(
        self, chat_id: int, phase_type: str, phase_index: int, msg_id: int,
    ) -> None:
        """Store the message ID for a phase (idempotent on re-set)."""
        key = self._phase_key(phase_type, phase_index)
        self._state[chat_id][key] = msg_id

    def has_phase(self, chat_id: int, phase_type: str, phase_index: int) -> bool:
        """Check if a phase has a message (was already created)."""
        key = self._phase_key(phase_type, phase_index)
        return key in self._state.get(chat_id, {})

    # ── Tool messages ───────────────────────────────────────────────────

    def get_tool_msg_id(self, chat_id: int, tool_id: str) -> int | None:
        return self._tool_msgs.get(chat_id, {}).get(tool_id)

    def set_tool_msg_id(self, chat_id: int, tool_id: str, msg_id: int) -> None:
        self._tool_msgs[chat_id][tool_id] = msg_id

    # ── Phase management ────────────────────────────────────────────────

    def reset_phases(self, chat_id: int) -> None:
        """Reset reasoning and content phase tracking for this chat.

        Called after a tool call. Keeps tool messages but clears all
        reasoning and content phase entries so new messages are created.
        """
        state = self._state.get(chat_id, {})
        keys_to_remove = [k for k in state if not k.startswith("tool:")]
        for k in keys_to_remove:
            del state[k]

    def get_all_msg_ids(self, chat_id: int) -> list[int]:
        """Get all message IDs tracked for a chat (for clearing)."""
        ids: list[int] = []
        state = self._state.get(chat_id, {})
        tool_state = self._tool_msgs.get(chat_id, {})
        for v in state.values():
            if v is not None:
                ids.append(v)
        for v in tool_state.values():
            if v is not None:
                ids.append(v)
        return ids

    def cleanup(self, chat_id: int) -> None:
        """Remove all state for a chat."""
        self._state.pop(chat_id, None)
        self._tool_msgs.pop(chat_id, None)
