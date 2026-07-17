"""Per-session coordination for vectorization and destructive cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass(slots=True)
class _SessionArtifactState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class SessionArtifactCoordinator:
    """Serialize artifact mutations by session within one application event loop.

    A state remains registered while a task holds or waits for its lock. The last
    participant removes it, so sessions that become inactive do not accumulate.
    """

    def __init__(self) -> None:
        self._states: dict[str, _SessionArtifactState] = {}

    @asynccontextmanager
    async def coordinate(self, session_id: str) -> AsyncIterator[None]:
        if not session_id:
            raise ValueError("session_id is required")

        state = self._states.get(session_id)
        if state is None:
            state = _SessionArtifactState()
            self._states[session_id] = state
        state.users += 1

        try:
            async with state.lock:
                yield
        finally:
            state.users -= 1
            if state.users == 0 and self._states.get(session_id) is state:
                del self._states[session_id]

    @property
    def tracked_session_count(self) -> int:
        """Number of sessions with an active holder or waiter."""
        return len(self._states)
