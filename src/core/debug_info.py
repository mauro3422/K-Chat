"""Structured debug info replacing the mutable dict bag."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
