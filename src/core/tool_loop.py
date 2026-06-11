import logging
import json
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Callable

from src.tools import TOOLS
from src.core import _deps
from src.core._deps import save_message

logger = logging.getLogger(__name__)

MAX_TOOL_TURNS = 5
OUTPUT_CHUNK_SIZE = 12


@dataclass
class _ToolLoopContext:
    history: list[dict[str, Any]]
    model: str
    session_id: str | None = None
    tagged: bool = False
    debug: dict[str, Any] | None = None
    phases_output: list[dict[str, Any]] | None = None
    used_tools: list[str] | None = None
    tool_detail: list[dict[str, Any]] | None = None
    run_parallel_tools_fn: Callable[..., Any] | None = None
    tool_map: dict[str, Any] | None = None
    max_turns: int = 10


def _build_tool_calls_list(tool_calls_out: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            },
        }
        for tc in tool_calls_out
    ]


def _append_assistant_with_tools(history: list[dict[str, Any]], content: str | None, tool_calls_list: list[dict[str, Any]]) -> None:
    history.append({
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls_list,
    })


def _save_assistant_tool_calls(session_id: str | None, content: str | None, model: str, tool_calls_list: list[dict[str, Any]]) -> None:
    if session_id:
        save_message(
            session_id,
            "assistant",
            content,
            model=model,
            tool_calls=json.dumps(tool_calls_list, ensure_ascii=False)
        )


def _append_phase(phases_output: list[dict[str, Any]] | None, reasoning: str, tool_ids: list[str], content: str | None) -> None:
    if phases_output is not None:
        phases_output.append({
            "reasoning": reasoning,
            "tool_ids": list(tool_ids),
            "content": content or ""
        })


def _execute_tools(
    ctx: _ToolLoopContext,
    turn: int,
    phase_tool_ids: list[str],
    tool_calls: list[Any],
    content: str | None,
    reasoning: str,
) -> Generator[Any, None, None]:
    tcs_list = _build_tool_calls_list(tool_calls)
    _append_assistant_with_tools(ctx.history, content, tcs_list)
    _save_assistant_tool_calls(ctx.session_id, content, ctx.model, tcs_list)

    assert ctx.run_parallel_tools_fn is not None
    for event in ctx.run_parallel_tools_fn(
        tool_calls, ctx.session_id, turn, ctx.history, ctx.tool_detail,
        ctx.used_tools, phase_tool_ids, tagged=ctx.tagged, tool_map=ctx.tool_map
    ):
        yield event

    _append_phase(ctx.phases_output, reasoning, list(phase_tool_ids), content or "")
    phase_tool_ids.clear()


def _process_tool_turn(
    ctx: _ToolLoopContext,
    turn: int,
    phase_reasoning: str,
    phase_tool_ids: list[str],
    tool_calls_out: list[Any],
    accumulated: list[tuple[str, str]],
) -> Generator[Any, None, tuple[int, str]]:
    turn += 1
    assistant_content = "".join(
        t[1] for t in accumulated if t[0] == "content"
    ) or None

    yield from _execute_tools(ctx, turn, phase_tool_ids, tool_calls_out, assistant_content, phase_reasoning)
    phase_reasoning = ""
    return turn, phase_reasoning


def _process_stream_event(tipo: str, token: Any, accumulated: list[tuple[str, str]], total_reasoning: list[str], tagged: bool) -> Generator[Any, None, None]:
    accumulated.append((tipo, token))
    if tipo == "reasoning":
        total_reasoning.append(token)
    if tagged:
        yield (tipo, token)
    elif tipo == "content":
        yield token


def _process_llm_stream(
    history: list[dict[str, Any]],
    model: str,
    debug: dict[str, Any] | None,
    tagged: bool,
    total_reasoning: list[str],
) -> Generator[Any, None, tuple[list[tuple[str, str]], list[Any], list[Any], str]]:
    reasoning_out: list[Any] = []
    tool_calls_out: list[Any] = []
    stream_iter = _deps.llm_stream(
        history, model, reasoning_output=reasoning_out, tagged=True,
        tools=TOOLS, tool_calls_output=tool_calls_out, debug=debug
    )
    accumulated: list[tuple[str, str]] = []
    phase_reasoning = ""
    try:
        for tipo, token in stream_iter:
            yield from _process_stream_event(tipo, token, accumulated, total_reasoning, tagged)
            if tipo == "reasoning":
                phase_reasoning += token
    except Exception as e:
        logger.error("Error reading from stream: %s", e)
        raise
    return accumulated, reasoning_out, tool_calls_out, phase_reasoning


def run_tool_loop_streaming(
    history: list[dict[str, Any]],
    model: str,
    session_id: str | None,
    tagged: bool,
    debug: dict[str, Any] | None,
    phases_output: list[dict[str, Any]] | None,
    used_tools: list[str],
    tool_detail: list[dict[str, Any]],
    run_parallel_tools_fn: Any,
    tool_map: dict[str, Any],
    max_turns: int = MAX_TOOL_TURNS
) -> Generator[Any, None, None]:
    """Tool loop for streaming path. Yields NDJSON events."""
    ctx = _ToolLoopContext(
        history=history, model=model, session_id=session_id, tagged=tagged,
        debug=debug, phases_output=phases_output, used_tools=used_tools,
        tool_detail=tool_detail, run_parallel_tools_fn=run_parallel_tools_fn,
        tool_map=tool_map, max_turns=max_turns,
    )
    turn = 0
    phase_reasoning = ""
    phase_tool_ids = []
    total_reasoning = []

    prev_content: str | None = None

    while turn < ctx.max_turns:
        accumulated, reasoning_out, tool_calls_out, phase_reasoning = yield from _process_llm_stream(
            ctx.history, ctx.model, ctx.debug, ctx.tagged, total_reasoning,
        )

        curr_content = "".join(t[1] for t in accumulated if t[0] == "content") or None

        if curr_content and prev_content and curr_content == prev_content:
            logger.warning("Duplicate content detected (turn %d), breaking tool loop", turn)
            yield ("content", curr_content) if ctx.tagged else curr_content
            if phase_reasoning or curr_content:
                _append_phase(ctx.phases_output, phase_reasoning, [], curr_content)
            break

        prev_content = curr_content
        has_tool_call = bool(tool_calls_out)

        if has_tool_call:
            turn, phase_reasoning = yield from _process_tool_turn(
                ctx, turn, phase_reasoning, phase_tool_ids, tool_calls_out, accumulated,
            )
            continue
        else:
            final_content = "".join(
                t[1] for t in accumulated if t[0] == "content"
            ) or ""
            if phase_reasoning or final_content:
                _append_phase(ctx.phases_output, phase_reasoning, [], final_content)
            break

    if ctx.debug is not None:
        ctx.debug["tool_calls"] = ctx.tool_detail
        ctx.debug["reasoning"] = "".join(total_reasoning)


def _process_sync_turn(
    ctx: _ToolLoopContext,
    turn: int,
    phase_reasoning: str,
    phase_tool_ids: list[str],
    result: Any,
) -> Generator[Any, None, tuple[int, str, Any]]:
    turn += 1
    rc = getattr(result.message, 'reasoning_content', None)
    if rc and ctx.tagged:
        yield ("reasoning", rc)
        phase_reasoning += rc
    if result.message.content:
        interim = result.message.content
        if ctx.tagged:
            yield ("content", interim)
        phase_reasoning += interim

    tool_calls = result.message.tool_calls or []
    yield from _execute_tools(ctx, turn, phase_tool_ids, tool_calls, result.message.content, phase_reasoning)

    result = _deps.llm_chat(ctx.history, ctx.model, tools=TOOLS)
    return turn, phase_reasoning, result


def _yield_chunked_content(
    full: str, tagged: bool, phases_output: list[dict[str, Any]] | None, final_reasoning: str
) -> Generator[Any, None, None]:
    if final_reasoning and tagged:
        yield ("reasoning", final_reasoning)
        _append_phase(phases_output, final_reasoning, [], full)
    for i in range(0, len(full), OUTPUT_CHUNK_SIZE):
        token = full[i:i + OUTPUT_CHUNK_SIZE]
        if tagged:
            yield ("content", token)
        else:
            yield token


def _yield_stream_fallback(
    history: list[dict[str, Any]], model: str, tagged: bool
) -> Generator[Any, None, str]:
    reasoning_out: list[str] = []
    for item in _deps.llm_stream(history, model, reasoning_output=reasoning_out, tagged=tagged):
        if tagged:
            tipo, token = item
            yield (tipo, token)
        else:
            yield item
    return "".join(reasoning_out)


def run_tool_loop_sync(
    history: list[dict[str, Any]],
    model: str,
    session_id: str | None,
    tagged: bool,
    debug: dict[str, Any] | None,
    phases_output: list[dict[str, Any]] | None,
    used_tools: list[str],
    tool_detail: list[dict[str, Any]],
    run_parallel_tools_fn: Any,
    tool_map: dict[str, Any],
    max_turns: int = MAX_TOOL_TURNS
) -> Generator[Any, None, None]:
    """Tool loop for synchronous path (tests). Yields NDJSON events."""
    ctx = _ToolLoopContext(
        history=history, model=model, session_id=session_id, tagged=tagged,
        debug=debug, phases_output=phases_output, used_tools=used_tools,
        tool_detail=tool_detail, run_parallel_tools_fn=run_parallel_tools_fn,
        tool_map=tool_map, max_turns=max_turns,
    )
    turn = 0
    phase_reasoning = ""
    phase_tool_ids = []
    final_reasoning = ""

    result = _deps.llm_chat(ctx.history, ctx.model, tools=TOOLS, debug=ctx.debug)
    while result.finish_reason == "tool_calls" and turn < ctx.max_turns:
        turn, phase_reasoning, result = yield from _process_sync_turn(
            ctx, turn, phase_reasoning, phase_tool_ids, result,
        )

    if ctx.used_tools:
        logger.info("Using: %s", ", ".join(ctx.used_tools))

    final_reasoning = getattr(result.message, 'reasoning_content', None) or ""
    content_str = ""
    if result.message.content:
        content_str = result.message.content
        yield from _yield_chunked_content(content_str, ctx.tagged, ctx.phases_output, final_reasoning)
    else:
        final_reasoning = yield from _yield_stream_fallback(ctx.history, ctx.model, ctx.tagged)

    ctx.history.append({
        "role": "assistant",
        "content": content_str,
        "tool_calls": [],
    })
    if ctx.session_id:
        save_message(
            ctx.session_id, "assistant", content_str,
            model=ctx.model, tool_calls="[]"
        )

    if ctx.debug is not None:
        ctx.debug["tool_calls"] = ctx.tool_detail
        ctx.debug["reasoning"] = final_reasoning
