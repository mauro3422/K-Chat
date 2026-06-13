"""Tool history operations."""

from src.memory.repos import Repositories, get_repos


def get_tool_history(session_id: str, limit: int = 10, repos: Repositories | None = None) -> list:
    """Obtiene el historial de tool calls de una sesión."""
    r = repos or get_repos()
    return r.tool_calls.get_history(session_id, limit)
