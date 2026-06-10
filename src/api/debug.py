"""Debug operations."""

from typing import Any

from src.memory.repositories import DebugRepository
from src.api._repos import _get_repo


def save_debug_info(session_id: str, data: dict[str, Any]) -> None:
    """Guarda información de depuración de una sesión."""
    return _get_repo(DebugRepository, "debug").save_info(session_id, data)


def get_debug_info(session_id: str) -> dict[str, Any]:
    """Obtiene información de depuración de una sesión."""
    return _get_repo(DebugRepository, "debug").get_info(session_id)
