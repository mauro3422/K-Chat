import json
from typing import Any
from src.memory.repositories import MessageRepository, ToolCallRepository

_message_repo: MessageRepository | None = None
_tool_call_repo: ToolCallRepository | None = None


def _get_message_repo() -> MessageRepository:
    global _message_repo
    if _message_repo is None:
        _message_repo = MessageRepository()
    return _message_repo


def _get_tool_call_repo() -> ToolCallRepository:
    global _tool_call_repo
    if _tool_call_repo is None:
        _tool_call_repo = ToolCallRepository()
    return _tool_call_repo


def _persist_tool_result(tc: Any, name: str, args: dict[str, Any], session_id: str, turn: int, history: list[dict[str, Any]], tool_detail: list[dict[str, Any]], tool_result: str, status: str) -> None:
    tool_detail.append({"name": name, "args": args, "status": status, "result_truncated": tool_result[:300]})
    if session_id:
        _get_tool_call_repo().log(session_id, name, json.dumps(args, ensure_ascii=False), status, turn=turn)
        _get_message_repo().save(session_id, "tool", tool_result, model=None, tool_call_id=tc.id)
    history.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})


def _persist_tool_results(
    tcs_info: list[tuple[Any, str, dict[str, Any]]],
    results: dict[str, tuple[str, str]],
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
) -> None:
    tool_call_repo = _get_tool_call_repo()
    message_repo = _get_message_repo()
    with tool_call_repo._transaction():
        for tc, name, args in tcs_info:
            tool_result, status = results.get(tc.id, ("[ERROR]: Resultado faltante para tool call", "error"))
            tool_detail.append({"name": name, "args": args, "status": status, "result_truncated": tool_result[:300]})
            if session_id:
                tool_call_repo.log(session_id, name, json.dumps(args, ensure_ascii=False), status, turn=turn)
                message_repo.save(session_id, "tool", tool_result, model=None, tool_call_id=tc.id)
            history.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})
