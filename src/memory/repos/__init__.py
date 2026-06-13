import sqlite3
from dataclasses import dataclass

from src.memory.repos.base import _BaseRepository
from src.memory.repos.debug_repository import DebugRepository
from src.memory.repos.message_repository import MessageRecord, MessageRepository
from src.memory.repos.saved_widget_repository import SavedWidgetRepository
from src.memory.repos.session_repository import SessionRepository
from src.memory.repos.tool_call_repository import ToolCallRepository
from src.memory.repos.memory_index_repository import MemoryIndexRepository
from src.memory.repos.widget_state_repository import WidgetStateRepository


@dataclass
class Repositories:
    messages: MessageRepository
    sessions: SessionRepository
    tool_calls: ToolCallRepository
    widget_states: WidgetStateRepository
    debug: DebugRepository
    saved_widgets: SavedWidgetRepository
    memory_index: MemoryIndexRepository


def get_repos(conn: sqlite3.Connection | None = None) -> Repositories:
    """Get all repositories, optionally sharing a single connection."""
    return Repositories(
        messages=MessageRepository(conn),
        sessions=SessionRepository(conn),
        tool_calls=ToolCallRepository(conn),
        widget_states=WidgetStateRepository(conn),
        debug=DebugRepository(conn),
        saved_widgets=SavedWidgetRepository(conn),
        memory_index=MemoryIndexRepository(conn),
    )


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
