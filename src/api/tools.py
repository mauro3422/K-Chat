"""Tool history operations."""

from src.memory.repos import Repositories


def get_tool_history(session_id: str, limit: int = 10, *, repos: Repositories) -> list:
    """Obtiene el historial de tool calls de una sesión."""
    return repos.tool_calls.get_history(session_id, limit)
