"""Shared types across all layers.

Canonical definitions live in ``src._types`` for neutral access.
Re-exported here so older imports keep working during the transition.
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
