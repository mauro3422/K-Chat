"""Tool history operations."""

from src.memory.repos import ToolCallRepository
from src.api._repos import _get_repo


def get_tool_history(session_id: str, limit: int = 10) -> list:
    """Obtiene el historial de tool calls de una sesión."""
    return _get_repo(ToolCallRepository, "tool_call").get_history(session_id, limit)
