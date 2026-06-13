"""Contracts for session operations."""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.repos import Repositories, SessionRepository


@dataclass(slots=True)
class SessionOpsDeps:
    """Optional dependency bundle for session operations."""

    session_repo: SessionRepository | None = None
    repos: Repositories | None = None
