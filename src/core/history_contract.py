"""Contracts for history reconstruction."""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from pydantic import BaseModel, Field

from src.memory.repos import MessageRepository

class HistoryMessage(BaseModel):
    role: str
    content: str | None
    created_at: str
    reasoning: str = ""
    phases: str = "[]"
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None

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
