"""LogEvent model for LogBus."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogEvent:
    """A structured log event with correlation fields."""
    level: str        # ERROR, WARN, INFO, DEBUG
    module: str       # e.g. "gateway", "chat", "llm", "tool", "web"
    msg: str
    session_id: str | None = None
    request_id: str | None = None
    data: dict[str, Any] | None = None
    duration_ms: float | None = None
    ts: float = 0.0  # set automatically if 0

    def __post_init__(self) -> None:
        if self.ts == 0.0:
            import time
            self.ts = time.time()
