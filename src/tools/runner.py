from __future__ import annotations

import json
import logging
import asyncio
import inspect
from datetime import datetime
from collections.abc import AsyncGenerator
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING

from src.tools._rate_limiter import _check_rate_limit
from src.tools._tool_parser import _parse_tool_call
from src.tools._tool_persister import _persist_tool_results
from src.tools._contract import HistoryMessage

if TYPE_CHECKING:
    from src.memory.repos import Repositories

logger: logging.Logger = logging.getLogger(__name__)


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@runtime_checkable
class ToolRunnerProtocol(Protocol):
    """Protocol for the run_parallel_tools function."""
    async def __call__(
        self,
        tool_calls: list[Any],
        session_id: str,
        turn: int,
        history: list[dict[str, Any]],
        tool_detail: list[dict[str, Any]],
        used_tools: list[str],
        phase_tool_ids: list[str],
        repos: 'Repositories',
        tagged: bool = False,
        tool_map: dict[str, Any] | None = None,
        skill_registry: Any | None = None,
        invalidate_cache_fn: Any | None = None,
        lan_request_signer: Any | None = None,
    ) -> AsyncGenerator[Any, None]: ...


async def _execute_tool_batch(
    tcs_info: list[tuple[Any, str, dict[str, Any]]],
    tool_map: dict[str, Any],
    session_id: str,
    tagged: bool,
    results: dict[str, tuple[str, str]],
    repos: 'Repositories',
    skill_registry: Any | None = None,
    invalidate_cache_fn: Any | None = None,
    lan_request_signer: Any | None = None,
) -> AsyncGenerator[Any, None]:
    async def wrap_tool(tc, name, args):
        try:
            tool_result = await _await_if_needed(
                tool_map[name](
                    **args,
                    _session_id=session_id,
                    _repos=repos,
                    _skill_registry=skill_registry,
                    _invalidate_cache_fn=invalidate_cache_fn,
                    _lan_request_signer=lan_request_signer,
                )
            )
            status = "error" if tool_result and tool_result.startswith("[ERROR]") else "ok"
        except asyncio.TimeoutError:
            logger.warning("Tool execution timed out for '%s'", name)
            tool_result = f"[ERROR in {name}]: Timeout after 60 seconds."
            status = "error"
        except Exception:
            logger.exception("Tool execution failed for '%s'", name)
            tool_result = f"[ERROR in {name}]: Internal error executing tool."
            status = "error"
        if tool_result is None:
            tool_result = f"[ERROR in {name}]: Tool returned None."
            status = "error"
        elif len(tool_result) > 30000:
            tool_result = tool_result[:30000] + "\n...[truncated]"
        return tc, name, tool_result, status

    tasks = [wrap_tool(tc, name, args) for tc, name, args in tcs_info]
    if not tasks:
        return

    outputs = [await t for t in tasks]
    for tc, name, tool_result, status in outputs:
        results[tc.id] = (tool_result, status)
        if tagged:
            yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": status}))


def _prepare_rate_limiters(session_id: str, tcs_info: list[tuple[Any, str, dict[str, Any]]]) -> tuple[bool, str]:
    """Check rate limits per tool and globally. Returns (ok, message)."""
    for _tc, name, _args in tcs_info:
        ok, msg = _check_rate_limit(session_id, tool_name=name)
        if not ok:
            return ok, msg
    return True, ""


async def _yield_tool_error_events(
    tcs_info: list[tuple[Any, str, dict[str, Any]]],
    error_msg: str,
    tagged: bool,
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
    repos: 'Repositories',
) -> AsyncGenerator[Any, None]:
    """Yield error events for tools that failed (parse error, rate limit)."""
    tool_call_repo = repos.tool_calls
    for tc, name, args in tcs_info:
        display_name = name or "unknown"
        if tagged:
            yield ("tool_call", json.dumps({"id": tc.id, "name": display_name, "status": "calling"}))
            yield ("tool_call", json.dumps({"id": tc.id, "name": display_name, "status": "error"}))
        if session_id:
            await tool_call_repo.log(session_id, display_name, json.dumps(args, ensure_ascii=False), "error", turn=turn)
        history.append(HistoryMessage(
            role="tool",
            content=error_msg,
            tool_call_id=tc.id,
            created_at=datetime.now().isoformat()
        ))
        tool_detail.append({"name": display_name, "args": args, "status": "error", "result_truncated": error_msg[:300]})


async def _execute_and_persist_tools(
    tcs_info: list[tuple[Any, str, dict[str, Any]]],
    tool_map: dict[str, Any],
    session_id: str,
    turn: int,
    tagged: bool,
    repos: 'Repositories',
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
    skill_registry: Any | None = None,
    invalidate_cache_fn: Any | None = None,
    lan_request_signer: Any | None = None,
) -> AsyncGenerator[Any, None]:
    """Execute tools in batch and persist results."""
    results: dict[str, tuple[str, str]] = {}
    async for event in _execute_tool_batch(
        tcs_info,
        tool_map,
        session_id,
        tagged,
        results,
        repos=repos,
        skill_registry=skill_registry,
        invalidate_cache_fn=invalidate_cache_fn,
        lan_request_signer=lan_request_signer,
    ):
        yield event
    await _persist_tool_results(tcs_info, results, session_id, turn, history, tool_detail, repos)


async def run_parallel_tools(
    tool_calls: list[Any],
    session_id: str,
    turn: int,
    history: list[dict[str, Any]],
    tool_detail: list[dict[str, Any]],
    used_tools: list[str],
    phase_tool_ids: list[str],
    repos: 'Repositories',
    tagged: bool = False,
    tool_map: dict[str, Any] | None = None,
    skill_registry: Any | None = None,
    invalidate_cache_fn: Any | None = None,
    lan_request_signer: Any | None = None,
) -> AsyncGenerator[Any, None]:
    import src.tools
    if tool_map is None:
        tool_map = src.tools.get_default_registry().tool_map

    tcs_info: list[tuple[Any, str, dict[str, Any]]] = []
    for tc in tool_calls:
        name, args, error = _parse_tool_call(tc, tool_map)
        if error:
            async for event in _yield_tool_error_events(
                [(tc, name, args)], error, tagged, session_id, turn, history, tool_detail, repos
            ):
                yield event
            continue

        if name not in used_tools:
            used_tools.append(name)
        tcs_info.append((tc, name, args))
        if tagged:
            yield ("tool_call", json.dumps({"id": tc.id, "name": name, "args": args, "status": "calling"}))
            phase_tool_ids.append(tc.id)

    ok, msg = _prepare_rate_limiters(session_id, tcs_info)
    if not ok:
        async for event in _yield_tool_error_events(
            tcs_info, msg, tagged, session_id, turn, history, tool_detail, repos
        ):
            yield event
        return

    async for event in _execute_and_persist_tools(
        tcs_info, tool_map, session_id, turn, tagged, repos, history, tool_detail,
        skill_registry=skill_registry,
        invalidate_cache_fn=invalidate_cache_fn,
        lan_request_signer=lan_request_signer,
    ):
        yield event
