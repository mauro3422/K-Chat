"""Message operations."""

from src.memory.repos import MessageRecord, Repositories


def save_message_record(record: MessageRecord, *, repos: Repositories) -> None:
    """Guarda un mensaje usando el contrato explícito MessageRecord."""
    return repos.messages.save_record(record)


def get_session_messages(session_id: str, limit: int = 500, *, repos: Repositories) -> list:
    """Obtiene los mensajes de una sesión ordenados por id."""
    return repos.messages.get_session_messages(session_id, limit)
