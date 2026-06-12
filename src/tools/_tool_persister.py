import json
from typing import Any
from src.memory.repos import ToolCallRepository


def _persist_tool_results(
    tcs_info: list[tuple[Any, str, dict[str, Any]]],
    results: dict[str, tuple[str, str]],
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
) -> None:
    from src.api._repos import _get_repo
    repo = _get_repo(ToolCallRepository, "tool_call")
    for tc, name, args in tcs_info:
        tool_result, status = results.get(tc.id, ("[ERROR]: Missing", "error"))
        tool_detail.append({"name": name, "args": args, "status": status, "result_truncated": tool_result[:300]})
        if session_id:
            repo.record_execution(
                session_id,
                name,
                json.dumps(args, ensure_ascii=False),
                status,
                tool_result,
                turn=turn,
                tool_call_id=tc.id,
            )
        history.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})
