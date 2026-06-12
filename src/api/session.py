"""Session operations."""

from src.memory.repos import SessionRepository

_SESSION_REPO = SessionRepository()


def ensure_session(session_id: str) -> None:
    """Asegura que una sesión exista en la base de datos."""
    return _SESSION_REPO.ensure(session_id)


def rename_session(session_id: str, name: str) -> None:
    """Renombra una sesión existente."""
    return _SESSION_REPO.rename(session_id, name)


def delete_session(session_id: str) -> None:
    """Elimina una sesión y todos sus mensajes y tool calls."""
    return _SESSION_REPO.delete(session_id)


def get_sessions(limit: int = 50) -> list:
    """Retorna la lista de sesiones ordenadas por última actividad."""
    return _SESSION_REPO.get_all(limit)
