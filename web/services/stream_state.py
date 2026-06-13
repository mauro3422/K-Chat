"""State container for the backend chat stream."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class StreamState:
    """Accumulates streamed assistant text and persistence timing."""

    full_content: str = ""
    full_reasoning: str = ""
    persisted: bool = False
    last_persisted_at: float = field(default_factory=time.monotonic)
    save_interval: float = 30.0

    def append(self, kind: str, token: str) -> None:
        if kind == "reasoning":
            self.full_reasoning += token
        elif kind == "content":
            self.full_content += token

    def reset_on_tool_call(self) -> None:
        self.full_content = ""
        self.full_reasoning = ""

    def has_output(self) -> bool:
        return bool(self.full_content or self.full_reasoning)

    def should_persist(self, now: float) -> bool:
        return self.has_output() and (now - self.last_persisted_at > self.save_interval)

    def mark_persisted(self, now: float) -> None:
        self.persisted = True
        self.last_persisted_at = now
