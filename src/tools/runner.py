import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Generator
from typing import Any
from src.tools._rate_limiter import _check_rate_limit
from src.tools._tool_parser import _parse_tool_call
from src.tools._tool_persister import _persist_tool_results
from src.constants import TOOL_HEARTBEAT_INTERVAL
from src.memory.repos import get_repos, Repositories

logger: logging.Logger = logging.getLogger(__name__)

_POLL_INTERVAL: float = 0.5


def _execute_tool_batch(tcs_info: list[tuple[Any, str, dict[str, Any]]], tool_map: dict[str, Any], session_id: str, tagged: bool, results: dict[str, tuple[str, str]]) -> Generator[Any, None, None]:
    with ThreadPoolExecutor(max_workers=max(1, len(tcs_info))) as pool:
        futs = {}
        for tc, name, args in tcs_info:
            futs[pool.submit(tool_map[name], **args, _session_id=session_id)] = (tc, name)
        remaining = set(futs.keys())
        last_heartbeat = time.monotonic()
        while remaining:
            done = {fut for fut in remaining if fut.done()}
            if done:
                for fut in done:
                    tc, name = futs[fut]
                    try:
                        tool_result = fut.result(timeout=0)
                        status = "error" if tool_result and tool_result.startswith("[ERROR]") else "ok"
                    except TimeoutError:
                        logger.warning("Tool execution timed out for '%s'", name)
                        tool_result = f"[ERROR en {name}]: Timeout después de 60 segundos."
                        status = "error"
                    except Exception:
                        logger.exception("Tool execution failed for '%s'", name)
                        tool_result = f"[ERROR en {name}]: Error interno al ejecutar el tool."
                        status = "error"
                    if len(tool_result) > 30000:
                        tool_result = tool_result[:30000] + "\n...[truncado]"
                    results[tc.id] = (tool_result, status)
                    if tagged:
                        yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": status}))
                remaining -= done
            if remaining:
                now = time.monotonic()
                if tagged and now - last_heartbeat >= TOOL_HEARTBEAT_INTERVAL:
                    yield ("heartbeat", "")
                    last_heartbeat = now
                time.sleep(_POLL_INTERVAL)


def _prepare_tool_calls(
    tool_calls: list[Any],
    tool_map: dict[str, Any],
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
    used_tools: list[str],
    tagged: bool,
    phase_tool_ids: list[str],
    repos: Repositories | None = None,
) -> Generator[Any, None, list[tuple[Any, str, dict[str, Any]]]]:
    tcs_info: list[tuple[Any, str, dict[str, Any]]] = []
    tool_call_repo = (repos or get_repos()).tool_calls
    for tc in tool_calls:
        name, args, error = _parse_tool_call(tc, tool_map)
        if error:
            if tagged:
                yield ("tool_call", json.dumps({"id": tc.id, "name": name or "unknown", "status": "calling"}))
                yield ("tool_call", json.dumps({"id": tc.id, "name": name or "unknown", "status": "error"}))
            if session_id:
                tool_call_repo.log(session_id, name or "unknown", json.dumps(args, ensure_ascii=False), "error", turn=turn)
            history.append({"role": "tool", "content": error, "tool_call_id": tc.id})
            tool_detail.append({"name": name or "unknown", "args": args, "status": "error", "result_truncated": error[:300]})
            continue

        if name not in used_tools:
            used_tools.append(name)
        tcs_info.append((tc, name, args))
        if tagged:
            yield ("tool_call", json.dumps({"id": tc.id, "name": name, "args": args, "status": "calling"}))
            phase_tool_ids.append(tc.id)
    return tcs_info


def run_parallel_tools(
    tool_calls: list[Any],
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
    used_tools: list[str],
    phase_tool_ids: list[str],
    tagged: bool = False,
    tool_map: dict[str, Any] | None = None,
    repos: Repositories | None = None,
) -> Generator[Any, None, None]:
    import src.tools
    if tool_map is None:
        tool_map = src.tools.TOOL_MAP

    tcs_info = yield from _prepare_tool_calls(
        tool_calls, tool_map, session_id, turn, history, tool_detail, used_tools, tagged, phase_tool_ids, repos,
    )

    results: dict[str, tuple[str, str]] = {}
    tool_call_repo = (repos or get_repos()).tool_calls

    ok, msg = _check_rate_limit(session_id)
    if not ok:
        for tc, name, args in tcs_info:
            if tagged:
                yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": "calling"}))
                yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": "error"}))
            if session_id:
                tool_call_repo.log(session_id, name, json.dumps(args, ensure_ascii=False), "error", turn=turn)
            history.append({"role": "tool", "content": msg, "tool_call_id": tc.id})
            tool_detail.append({"name": name, "args": args, "status": "error", "result_truncated": msg[:300]})
        return

    yield from _execute_tool_batch(tcs_info, tool_map, session_id, tagged, results)

    _persist_tool_results(tcs_info, results, session_id, turn, history, tool_detail)
