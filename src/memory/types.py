"""Shared types across all layers. Canonical source of truth for domain types."""

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


@dataclass
class DebugInfo:
    """Container for debug metadata passed through the chat pipeline.

    Replaces the untyped ``dict[str, Any]`` that was previously mutated
    by orchestrator, tool_loop, llm/client, and message_persister.
    """

    model: str = ""
    session_id: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    history_before: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
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
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "phases": self.phases,
        }
