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

Message IDs are also persisted to SQLite so they survive bot restarts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from channels.telegram.protocols import TelegramAPIClientProtocol

if TYPE_CHECKING:
    from src.memory.repos.telegram_msg_id_repository import TelegramMsgIdRepo


class MessageManager:
    """Tracks message IDs per (chat, phase_type, phase_index).

    This is a pure state manager — it does NOT make API calls. The
    caller (TelegramRenderer) creates messages via the API client
    and tells the manager to store the resulting IDs.
    """

    def __init__(self, repo: TelegramMsgIdRepo | None = None) -> None:
        self._repo = repo
        # {chat_id: {"reasoning:0": msg_id, "content:2": msg_id, ...}}
        self._state: dict[int, dict[str, int]] = defaultdict(dict)
        # {chat_id: {"tool:call_X": msg_id}}
        self._tool_msgs: dict[int, dict[str, int]] = defaultdict(dict)
        # Continuation messages (overflow chunks beyond 4000 chars).
        # {chat_id: {"reasoning:0": [msg_id, ...], "content:2": [msg_id, ...]}}
        # Each element is a 📎 continuation message for that phase.
        self._continuations: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))

    # ── Phase tracking ──────────────────────────────────────────────────

    def _phase_key(self, phase_type: str, phase_index: int) -> str:
        return f"{phase_type}:{phase_index}"

    def get_msg_id(self, chat_id: int, phase_type: str, phase_index: int) -> int | None:
        """Get the message ID for a specific phase, or None."""
        key = self._phase_key(phase_type, phase_index)
        return self._state.get(chat_id, {}).get(key)

    async def set_msg_id(
        self, chat_id: int, phase_type: str, phase_index: int, msg_id: int,
    ) -> None:
        """Store the message ID for a phase (idempotent on re-set).

        Persists to both in-memory state and SQLite.
        """
        key = self._phase_key(phase_type, phase_index)
        self._state[chat_id][key] = msg_id
        if self._repo is not None:
            await self._repo.save(chat_id, key, msg_id)

    def has_phase(self, chat_id: int, phase_type: str, phase_index: int) -> bool:
        """Check if a phase has a message (was already created)."""
        key = self._phase_key(phase_type, phase_index)
        return key in self._state.get(chat_id, {})

    # ── Tool messages ───────────────────────────────────────────────────

    def get_tool_msg_id(self, chat_id: int, tool_id: str) -> int | None:
        return self._tool_msgs.get(chat_id, {}).get(tool_id)

    async def set_tool_msg_id(self, chat_id: int, tool_id: str, msg_id: int) -> None:
        """Store a tool message ID, persisting to both memory and SQLite."""
        self._tool_msgs[chat_id][tool_id] = msg_id
        if self._repo is not None:
            phase_key = f"tool:{tool_id}"
            await self._repo.save(chat_id, phase_key, msg_id)

    # ── Phase management ────────────────────────────────────────────────

    async def reset_phases(self, chat_id: int) -> None:
        """Reset reasoning and content phase tracking for this chat.

        Called after a tool call. Keeps tool messages but clears all
        reasoning and content phase entries so new messages are created.
        """
        state = self._state.get(chat_id, {})
        keys_to_remove = [k for k in state if not k.startswith("tool:")]
        for k in keys_to_remove:
            del state[k]
        # Also clear continuations for this chat
        self._continuations.pop(chat_id, None)

    # ── Generic message ID storage (for the inline renderer) ────────

    async def store_msg_id(self, chat_id: int, key: str, msg_id: int) -> None:
        """Store an arbitrary message ID for a chat (e.g. the main message).

        Key examples: ``"main"``, ``"cont:0"``, ``"tool:call_xxx"``.
        """
        self._state[chat_id][key] = msg_id
        if self._repo is not None:
            await self._repo.save(chat_id, key, msg_id)

    # ── Continuation messages (overflow beyond 4000 chars) ───────────

    def get_continuations(self, chat_id: int, phase_type: str, phase_index: int) -> list[int]:
        """Get continuation message IDs for a phase."""
        key = self._phase_key(phase_type, phase_index)
        return list(self._continuations.get(chat_id, {}).get(key, []))

    async def set_continuation(self, chat_id: int, phase_type: str, phase_index: int, msg_id: int, index: int) -> None:
        """Store a continuation message ID at a given overflow index."""
        key = self._phase_key(phase_type, phase_index)
        conts = self._continuations[chat_id][key]
        while len(conts) <= index:
            conts.append(0)
        conts[index] = msg_id
        if self._repo is not None:
            await self._repo.save(chat_id, f"{key}:cont{index}", msg_id)

    async def get_all_msg_ids(self, chat_id: int) -> list[int]:
        """Get all message IDs tracked for a chat (for clearing).

        Merges in-memory state with persisted DB rows so that IDs
        survive bot restarts.
        """
        seen: set[int] = set()
        ids: list[int] = []

        # Load from in-memory state
        state = self._state.get(chat_id, {})
        tool_state = self._tool_msgs.get(chat_id, {})
        for v in state.values():
            if v is not None and v not in seen:
                seen.add(v)
                ids.append(v)
        for v in tool_state.values():
            if v is not None and v not in seen:
                seen.add(v)
                ids.append(v)
        # Also include continuation messages
        for cont_list in self._continuations.get(chat_id, {}).values():
            for v in cont_list:
                if v and v not in seen:
                    seen.add(v)
                    ids.append(v)

        # Load from DB (covers IDs persisted before restart)
        if self._repo is not None:
            rows = await self._repo.get_all(chat_id)
            for _, msg_id in rows:
                if msg_id not in seen:
                    seen.add(msg_id)
                    ids.append(msg_id)

        return ids

    async def cleanup(self, chat_id: int) -> None:
        """Remove all state for a chat (memory + DB)."""
        self._state.pop(chat_id, None)
        self._tool_msgs.pop(chat_id, None)
        self._continuations.pop(chat_id, None)
        if self._repo is not None:
            await self._repo.delete_chat(chat_id)
