"""Session operations."""

from src.memory.repositories import SessionRepository
from src.api._repos import _get_repo


def ensure_session(session_id: str) -> None:
    """Asegura que una sesión exista en la base de datos."""
    return _get_repo(SessionRepository, "session").ensure(session_id)


def rename_session(session_id: str, name: str) -> None:
    """Renombra una sesión existente."""
    return _get_repo(SessionRepository, "session").rename(session_id, name)


def delete_session(session_id: str) -> None:
    """Elimina una sesión y todos sus mensajes y tool calls."""
    return _get_repo(SessionRepository, "session").delete(session_id)


def get_sessions(limit: int = 50) -> list:
    """Retorna la lista de sesiones ordenadas por última actividad."""
    return _get_repo(SessionRepository, "session").get_all(limit)
