"""Message operations."""

from typing import Any

from src.memory.repos import MessageRecord, MessageRepository

_MESSAGE_REPO = MessageRepository()


def save_message(*args: Any, **kwargs: Any) -> None:
    """Guarda un mensaje en la base de datos (acepta MessageRecord o args)."""
    repo = _MESSAGE_REPO
    if len(args) == 1 and isinstance(args[0], MessageRecord):
        return repo.save_record(args[0])
    return repo.save(*args, **kwargs)


def get_session_messages(session_id: str, limit: int = 500) -> list:
    """Obtiene los mensajes de una sesión ordenados por id."""
    return _MESSAGE_REPO.get_session_messages(session_id, limit)
