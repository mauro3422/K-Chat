"""Contracts for debug operations."""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.repos import DebugRepository


@dataclass(slots=True)
class DebugOpsDeps:
    """Optional dependency bundle for debug persistence."""

    debug_repo: DebugRepository | None = None
