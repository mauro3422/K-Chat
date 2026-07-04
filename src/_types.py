"""Neutral shared types across all layers.

Canonical location for cross-layer types. Leaf layers import from here
instead of from each other. Original locations (src.memory.types, etc.)
re-export from this module so older imports keep working during the transition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass
class MessageRecord:
    session_id: str = ""
    role: str = ""
    content: str = ""
    model: str | None = None
    reasoning: str = ""
    phases: str = "[]"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tool_calls: str | None = None
    tool_call_id: str | None = None


class HistoryMessage(BaseModel):
    """Message contract shared by core, tools, and LLM layers."""

    role: str
    content: str | None
    created_at: str
    reasoning: str = ""
    phases: str = "[]"
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    id: int | None = None

    def as_llm_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.tool_calls:  # exclude None and empty list
            msg["tool_calls"] = self.tool_calls
        if self.reasoning:
            msg["reasoning_content"] = self.reasoning
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        return msg


@dataclass
class DebugInfo:
    """Container for debug metadata passed through the chat pipeline."""

    model: str = ""
    session_id: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    history_before: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    auto_memories: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    phases: str = "[]"

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "session_id": self.session_id,
            "reasoning": self.reasoning,
            "tool_calls": self.tool_calls,
            "history_before": self.history_before,
            "system_prompt": self.system_prompt,
            "auto_memories": self.auto_memories,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "phases": self.phases,
        }


MessageRecord.__module__ = "src._types"
HistoryMessage.__module__ = "src._types"
DebugInfo.__module__ = "src._types"
