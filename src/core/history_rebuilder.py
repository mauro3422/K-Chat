from typing import Any
from src.context import build_system_prompt
from src.core.history_parser import _parse_rows, _sanitize_messages
from src.core.history_contract import HistoryRebuildDeps
from src.memory.repos import MessageRepository


def rebuild_history(
    session_id: str,
    model: str,
    messages_repo: MessageRepository | None = None,
    deps: HistoryRebuildDeps | None = None,
) -> list[dict[str, Any]]:
    _deps = deps or HistoryRebuildDeps(messages_repo=messages_repo)
    repo = _deps.messages_repo
    if repo is None:
        raise ValueError("messages_repo is required for rebuild_history()")
    rows = repo.get_session_messages(session_id)
    raw_msgs = _parse_rows(rows)
    sanitized = _sanitize_messages(raw_msgs)
    rebuilt = [build_system_prompt(model)]
    for msg in sanitized:
        if hasattr(msg, "as_llm_message"):
            rebuilt.append(msg.as_llm_message())
        elif isinstance(msg, dict):
            rebuilt.append(msg)
        else:
            rebuilt.append({
                "role": getattr(msg, "role", ""),
                "content": getattr(msg, "content", None),
                "created_at": getattr(msg, "created_at", ""),
            })
    return rebuilt
