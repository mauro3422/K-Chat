"""Contracts for history reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any

from src.memory.repos import MessageRepository


@dataclass(slots=True)
class HistoryMessage:
    role: str
    content: str | None
    created_at: str
    reasoning: str = ""
    phases: str = "[]"
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self) -> Iterable[str]:
        return ("role", "content", "created_at", "reasoning", "phases", "tool_calls", "tool_call_id")

    def as_llm_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.tool_calls is not None:
            msg["tool_calls"] = self.tool_calls
        if self.reasoning:
            msg["reasoning_content"] = self.reasoning
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        return msg


@dataclass(slots=True)
class HistoryRebuildDeps:
    """Optional dependency bundle for history reconstruction."""

    messages_repo: MessageRepository | None = None
