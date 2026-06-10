from typing import Any
from src.memory.repositories import MessageRepository
from src.context import build_system_prompt
from src.core.history_parser import _parse_rows, _sanitize_messages

_repo: MessageRepository | None = None


def _get_repo() -> MessageRepository:
    global _repo
    if _repo is None:
        _repo = MessageRepository()
    return _repo


def rebuild_history(session_id: str, model: str) -> list[dict[str, Any]]:
    rows = _get_repo().get_session_messages(session_id)
    raw_msgs = _parse_rows(rows)
    sanitized = _sanitize_messages(raw_msgs)
    return [build_system_prompt(model)] + sanitized
