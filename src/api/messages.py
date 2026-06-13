"""Message operations."""

from src.memory.repos import MessageRecord, Repositories, get_repos


def save_message_record(record: MessageRecord, repos: Repositories | None = None) -> None:
    """Guarda un mensaje usando el contrato explícito MessageRecord."""
    r = repos or get_repos()
    return r.messages.save_record(record)


def get_session_messages(session_id: str, limit: int = 500, repos: Repositories | None = None) -> list:
    """Obtiene los mensajes de una sesión ordenados por id."""
    r = repos or get_repos()
    return r.messages.get_session_messages(session_id, limit)
