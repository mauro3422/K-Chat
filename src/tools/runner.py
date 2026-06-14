import json
import logging
import asyncio
from datetime import datetime
from collections.abc import AsyncGenerator
from typing import Any
from src.tools._rate_limiter import _check_rate_limit
from src.tools._tool_parser import _parse_tool_call
from src.tools._tool_persister import _persist_tool_results
from src.config_loader import DEFAULT_CONFIG
from src.memory.repos import Repositories
from src.core.history_contract import HistoryMessage

logger: logging.Logger = logging.getLogger(__name__)


async def _execute_tool_batch(tcs_info: list[tuple[Any, str, dict[str, Any]]], tool_map: dict[str, Any], session_id: str, tagged: bool, results: dict[str, tuple[str, str]], repos: Repositories) -> AsyncGenerator[Any, None]:
    async def wrap_tool(tc, name, args):
        try:
            import inspect
            res = tool_map[name](**args, _session_id=session_id, _repos=repos)
            if inspect.iscoroutine(res):
                tool_result = await res
            else:
                tool_result = res
            status = "error" if tool_result and tool_result.startswith("[ERROR]") else "ok"
        except asyncio.TimeoutError:
            logger.warning("Tool execution timed out for '%s'", name)
            tool_result = f"[ERROR in {name}]: Timeout after 60 seconds."
            status = "error"
        except Exception:
            logger.exception("Tool execution failed for '%s'", name)
            tool_result = f"[ERROR in {name}]: Internal error executing tool."
            status = "error"
        if len(tool_result) > 30000:
            tool_result = tool_result[:30000] + "\n...[truncated]"
        return tc, name, tool_result, status

    tasks = [wrap_tool(tc, name, args) for tc, name, args in tcs_info]
    if not tasks:
        return

    # Use asyncio.gather for calling the now-async tool run methods.
    outputs = await asyncio.gather(*tasks)
    for tc, name, tool_result, status in outputs:
        results[tc.id] = (tool_result, status)
        if tagged:
            yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": status}))


async def run_parallel_tools(
    tool_calls: list[Any],
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
    used_tools: list[str],
    phase_tool_ids: list[str],
    repos: Repositories,
    tagged: bool = False,
    tool_map: dict[str, Any] | None = None,
) -> AsyncGenerator[Any, None]:
    import src.tools
    if tool_map is None:
        tool_map = src.tools.get_default_registry().tool_map

    tcs_info: list[tuple[Any, str, dict[str, Any]]] = []
    tool_call_repo = repos.tool_calls
    for tc in tool_calls:
        name, args, error = _parse_tool_call(tc, tool_map)
        if error:
            if tagged:
                yield ("tool_call", json.dumps({"id": tc.id, "name": name or "unknown", "status": "calling"}))
                yield ("tool_call", json.dumps({"id": tc.id, "name": name or "unknown", "status": "error"}))
            if session_id:
                await tool_call_repo.log(session_id, name or "unknown", json.dumps(args, ensure_ascii=False), "error", turn=turn)
            history.append(HistoryMessage(
                role="tool",
                content=error,
                tool_call_id=tc.id,
                created_at=datetime.now().isoformat()
            ))
            tool_detail.append({"name": name or "unknown", "args": args, "status": "error", "result_truncated": error[:300]})
            continue

        if name not in used_tools:
            used_tools.append(name)
        tcs_info.append((tc, name, args))
        if tagged:
            yield ("tool_call", json.dumps({"id": tc.id, "name": name, "args": args, "status": "calling"}))
            phase_tool_ids.append(tc.id)

    results: dict[str, tuple[str, str]] = {}

    ok, msg = _check_rate_limit(session_id)
    if not ok:
        for tc, name, args in tcs_info:
            if tagged:
                yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": "calling"}))
                yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": "error"}))
            if session_id:
                await tool_call_repo.log(session_id, name, json.dumps(args, ensure_ascii=False), "error", turn=turn)
            history.append(HistoryMessage(
                role="tool",
                content=msg,
                tool_call_id=tc.id,
                created_at=datetime.now().isoformat()
            ))
            tool_detail.append({"name": name, "args": args, "status": "error", "result_truncated": msg[:300]})
        return

    async for event in _execute_tool_batch(tcs_info, tool_map, session_id, tagged, results, repos=repos):
        yield event

    await _persist_tool_results(tcs_info, results, session_id, turn, history, tool_detail, repos)
