"""Tool history operations."""

from src.memory.repos import ToolCallRepository

_TOOL_CALL_REPO = ToolCallRepository()


def get_tool_history(session_id: str, limit: int = 10) -> list:
    """Obtiene el historial de tool calls de una sesión."""
    return _TOOL_CALL_REPO.get_history(session_id, limit)
