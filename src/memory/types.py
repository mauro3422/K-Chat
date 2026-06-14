"""Shared types across all layers.

Canonical definitions moved to ``src._types`` for neutral access.
Re-exported here for backward compatibility.
"""

from src._types import (
    MessageRecord,
    HistoryMessage,
    DebugInfo,
)

__all__ = [
    "MessageRecord",
    "HistoryMessage",
    "DebugInfo",
]
