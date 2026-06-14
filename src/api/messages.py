"""Message operations."""

from src.memory.repos import MessageRecord, Repositories


async def save_message_record(record: MessageRecord, *, repos: Repositories) -> None:
    """Guarda un mensaje usando el contrato explícito MessageRecord."""
    return await repos.messages.save_record(record)


async def get_session_messages(session_id: str, limit: int = 500, *, repos: Repositories) -> list:
    """Obtiene los mensajes de una sesión ordenados por id."""
    return await repos.messages.get_session_messages(session_id, limit)
