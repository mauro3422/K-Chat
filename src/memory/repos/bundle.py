"""Repository bundle for sessions.db plus shared memory access."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.memory.repos.protocols import (
    DebugRepositoryProtocol,
    MemoryIndexRepositoryProtocol,
    MessageRepositoryProtocol,
    SavedWidgetRepositoryProtocol,
    SessionRepositoryProtocol,
    ToolCallRepositoryProtocol,
    WidgetStateRepositoryProtocol,
)

if TYPE_CHECKING:
    from src.memory.repos_memory import MemoryRepositories


logger = logging.getLogger(__name__)


@dataclass
class Repositories:
    """All database repositories - sessions (local) + memory (shared)."""

    messages: MessageRepositoryProtocol
    sessions: SessionRepositoryProtocol
    tool_calls: ToolCallRepositoryProtocol
    widget_states: WidgetStateRepositoryProtocol
    debug: DebugRepositoryProtocol
    saved_widgets: SavedWidgetRepositoryProtocol
    memory_index: MemoryIndexRepositoryProtocol
    _memory: MemoryRepositories | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Keep memory.db construction lazy; most code paths only need sessions.db.
        pass

    @staticmethod
    def _close_memory_bundle(bundle: MemoryRepositories | None) -> None:
        if bundle is None:
            return
        close = getattr(bundle, "close", None)
        if callable(close):
            close()

    @property
    def memory(self) -> MemoryRepositories:
        if self._memory is None:
            from src.memory.repos_memory import MemoryRepositories

            self._memory = MemoryRepositories()
        return self._memory

    @memory.setter
    def memory(self, value: MemoryRepositories | None) -> None:
        if self._memory is value:
            return
        if self._memory is not None:
            try:
                self._close_memory_bundle(self._memory)
            except Exception:
                logger.warning("Failed to close replaced memory bundle", exc_info=True)
        self._memory = value

    def close(self) -> None:
        """Close cached resources owned by nested repositories."""
        if self._memory is None:
            return
        try:
            self._close_memory_bundle(self._memory)
        finally:
            # Drop the cached bundle so a later access can rebuild it cleanly.
            self._memory = None


def get_repos(conn=None) -> Repositories:
    from src.memory.repos.debug_repository import DebugRepository
    from src.memory.repos.message_repository import MessageRepository
    from src.memory.repos.memory_index_repository import MemoryIndexRepository
    from src.memory.repos.saved_widget_repository import SavedWidgetRepository
    from src.memory.repos.session_repository import SessionRepository
    from src.memory.repos.tool_call_repository import ToolCallRepository
    from src.memory.repos.widget_state_repository import WidgetStateRepository

    repos = Repositories(
        messages=MessageRepository(conn=conn),
        sessions=SessionRepository(conn=conn),
        tool_calls=ToolCallRepository(conn=conn),
        widget_states=WidgetStateRepository(conn=conn),
        debug=DebugRepository(conn=conn),
        saved_widgets=SavedWidgetRepository(conn=conn),
        memory_index=MemoryIndexRepository(conn=conn),
    )
    return repos
