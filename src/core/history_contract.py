"""Contracts for history reconstruction."""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.repos import MessageRepository
from src.tools._contract import HistoryMessage  # noqa: F401 — re-exported for backward compat


@dataclass(slots=True)
class HistoryRebuildDeps:
    """Optional dependency bundle for history reconstruction."""

    messages_repo: MessageRepository | None = None
