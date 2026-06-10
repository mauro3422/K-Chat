import json
from datetime import datetime
from typing import Any
from src.memory.repos import ToolCallRepository

_tool_call_repo: ToolCallRepository | None = None


def _get_tool_call_repo() -> ToolCallRepository:
    global _tool_call_repo
    if _tool_call_repo is None:
        _tool_call_repo = ToolCallRepository()
    return _tool_call_repo


def _persist_tool_results(
    tcs_info: list[tuple[Any, str, dict[str, Any]]],
    results: dict[str, tuple[str, str]],
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
) -> None:
    tool_call_repo = _get_tool_call_repo()
    conn = tool_call_repo._get_conn()
    try:
        for tc, name, args in tcs_info:
            tool_result, status = results.get(tc.id, ("[ERROR]: Missing", "error"))
            tool_detail.append({"name": name, "args": args, "status": status, "result_truncated": tool_result[:300]})
            if session_id:
                now = datetime.now().isoformat()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO tool_calls (session_id, tool_name, input, status, turn, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, name, json.dumps(args, ensure_ascii=False), status, turn, now)
                )
                cursor.execute(
                    "INSERT INTO messages (session_id, role, content, model, tool_call_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, "tool", tool_result, None, tc.id, now)
                )
            history.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
