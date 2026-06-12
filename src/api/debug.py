"""Debug operations."""

from typing import Any

from src.memory.repos import DebugRepository

_DEBUG_REPO = DebugRepository()


def save_debug_info(session_id: str, data: dict[str, Any]) -> None:
    """Guarda información de depuración de una sesión."""
    return _DEBUG_REPO.save_info(session_id, data)


def get_debug_info(session_id: str) -> dict[str, Any]:
    """Obtiene información de depuración de una sesión."""
    return _DEBUG_REPO.get_info(session_id)
