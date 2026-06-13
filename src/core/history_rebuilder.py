from typing import Any
from src.memory.repos import MessageRepository
from src.context import build_system_prompt
from src.core.history_parser import _parse_rows, _sanitize_messages

_MESSAGE_REPO = MessageRepository()


def rebuild_history(session_id: str, model: str, message_repo: MessageRepository | None = None) -> list[dict[str, Any]]:
    repo = message_repo or _MESSAGE_REPO
    rows = repo.get_session_messages(session_id)
    raw_msgs = _parse_rows(rows)
    sanitized = _sanitize_messages(raw_msgs)
    return [build_system_prompt(model)] + sanitized
