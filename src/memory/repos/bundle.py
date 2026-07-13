"""Repository bundle for sessions.db plus shared memory access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.memory.repos.base import _BaseRepository
from src.memory.repos.debug_repository import DebugRepository
from src.memory.repos.message_repository import MessageRecord, MessageRepository
from src.memory.repos.memory_index_repository import MemoryIndexRepository
from src.memory.repos.protocols import (
    DebugRepositoryProtocol,
    MemoryIndexRepositoryProtocol,
    MessageRepositoryProtocol,
    SavedWidgetRepositoryProtocol,
    SessionRepositoryProtocol,
    ToolCallRepositoryProtocol,
    WidgetStateRepositoryProtocol,
)
from src.memory.repos.saved_widget_repository import SavedWidgetRepository
from src.memory.repos.session_repository import SessionRepository
from src.memory.repos.tool_call_repository import ToolCallRepository
from src.memory.repos.widget_state_repository import WidgetStateRepository

if TYPE_CHECKING:
    from src.memory.repos_memory import MemoryRepositories


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
    memory: MemoryRepositories | None = None  # memory.db repos (lazy-initialized)

    def __post_init__(self) -> None:
        if self.memory is None:
            from src.memory.repos_memory import MemoryRepositories

            self.memory = MemoryRepositories()

    def close(self) -> None:
        """Close cached resources owned by nested repositories."""
        if self.memory is not None:
            self.memory.close()


def get_repos(conn=None) -> Repositories:
    from src.memory.repos_memory import get_memory_repos

    repos = Repositories(
        messages=MessageRepository(conn=conn),
        sessions=SessionRepository(conn=conn),
        tool_calls=ToolCallRepository(conn=conn),
        widget_states=WidgetStateRepository(conn=conn),
        debug=DebugRepository(conn=conn),
        saved_widgets=SavedWidgetRepository(conn=conn),
        memory_index=MemoryIndexRepository(conn=conn),
        memory=get_memory_repos(),
    )
    return repos


__all__ = [
    "_BaseRepository",
    "MessageRecord",
    "MessageRepository",
    "SessionRepository",
    "ToolCallRepository",
    "WidgetStateRepository",
    "MemoryIndexRepository",
    "DebugRepository",
    "SavedWidgetRepository",
    "Repositories",
    "get_repos",
]
