from __future__ import annotations

import json
from datetime import datetime
from typing import Any, TYPE_CHECKING

from src.tools._contract import HistoryMessage

if TYPE_CHECKING:
    from src.memory.repos import Repositories


async def _persist_tool_results(
    tcs_info: list[tuple[Any, str, dict[str, Any]]],
    results: dict[str, tuple[str, str]],
    session_id: str,
    turn: int,
    history: list[Any],
    tool_detail: list[dict[str, Any]],
    repos: 'Repositories',
) -> None:
    repo = repos.tool_calls
    for tc, name, args in tcs_info:
        tool_result, status = results.get(tc.id, ("[ERROR]: Missing", "error"))
        tool_detail.append({"name": name, "args": args, "status": status, "result_truncated": tool_result[:300]})
        if session_id:
            await repo.record_execution(
                session_id,
                name,
                json.dumps(args, ensure_ascii=False),
                status,
                tool_result,
                turn=turn,
                tool_call_id=tc.id,
            )
        history.append(HistoryMessage(
            role="tool",
            content=tool_result,
            tool_call_id=tc.id,
            created_at=datetime.now().isoformat()
        ))
