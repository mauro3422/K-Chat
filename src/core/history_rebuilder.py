from typing import Any
from typing import Any
from src.memory.repos import get_repos
from src.context import build_system_prompt
from src.core.history_parser import _parse_rows, _sanitize_messages


def rebuild_history(session_id: str, model: str) -> list[dict[str, Any]]:
    rows = get_repos().messages.get_session_messages(session_id)
    raw_msgs = _parse_rows(rows)
    sanitized = _sanitize_messages(raw_msgs)
    return [build_system_prompt(model)] + sanitized
