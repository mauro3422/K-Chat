import logging
import json
from datetime import datetime
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Callable

from src.constants import MAX_TOOL_TURNS, TOOL_OUTPUT_CHUNK_SIZE
from src.core.debug_info import DebugInfo
from src.memory.repos import Repositories
from src.core.history_contract import HistoryMessage

logger = logging.getLogger(__name__)

@dataclass
class _ToolLoopContext:
    history: list[dict[str, Any]]
    model: str
    session_id: str | None = None
    tagged: bool = False
    debug: DebugInfo | None = None
    phases_output: list[dict[str, Any]] | None = None
    used_tools: list[str] | None = None
    tool_detail: list[dict[str, Any]] | None = None
    run_parallel_tools_fn: Callable[..., Any] | None = None
    tool_map: dict[str, Any] | None = None
    repos: 'Repositories | None' = None
    max_turns: int = MAX_TOOL_TURNS
    llm_chat_fn: Callable[..., Any] | None = None
    llm_chat_stream_fn: Callable[..., Any] | None = None
    tool_defs: list[dict[str, Any]] | None = None


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


def _append_assistant_with_tools(history: list[Any], content: str | None, tool_calls_list: list[dict[str, Any]]) -> None:
    history.append(HistoryMessage(
        role="assistant",
        content=content,
        tool_calls=tool_calls_list,
        created_at=datetime.now().isoformat()
    ))


async def _save_assistant_tool_calls(
    session_id: str | None,
    content: str | None,
    model: str,
    tool_calls_list: list[dict[str, Any]],
    repos: 'Repositories | None' = None,
) -> None:
    if session_id and repos is not None:
        await repos.messages.save(
            session_id=session_id,
            role="assistant",
            content=content,
            model=model,
            tool_calls=json.dumps(tool_calls_list, ensure_ascii=False),
        )


def _append_phase(phases_output: list[dict[str, Any]] | None, reasoning: str, tool_ids: list[str], content: str | None) -> None:
    if phases_output is not None:
        phases_output.append({
            "reasoning": reasoning,
            "tool_ids": list(tool_ids),
            "content": content or ""
        })


async def _execute_tools(
    ctx: _ToolLoopContext,
    turn: int,
    phase_tool_ids: list[str],
    tool_calls: list[Any],
    content: str | None,
    reasoning: str,
) -> AsyncGenerator[Any, None]:
    tcs_list = _build_tool_calls_list(tool_calls)
    _append_assistant_with_tools(ctx.history, content, tcs_list)
    await _save_assistant_tool_calls(ctx.session_id, content, ctx.model, tcs_list, ctx.repos)

    assert ctx.run_parallel_tools_fn is not None
    async for event in ctx.run_parallel_tools_fn(
        tool_calls, ctx.session_id, turn, ctx.history, ctx.tool_detail,
        ctx.used_tools, phase_tool_ids, tagged=ctx.tagged, tool_map=ctx.tool_map,
        repos=ctx.repos,
    ):
        yield event

    _append_phase(ctx.phases_output, reasoning, list(phase_tool_ids), content or "")
    phase_tool_ids.clear()


async def run_tool_loop_streaming(
    history: list[dict[str, Any]],
    model: str,
    session_id: str | None,
    tagged: bool,
    debug: DebugInfo | None,
    phases_output: list[dict[str, Any]] | None,
    used_tools: list[str],
    tool_detail: list[dict[str, Any]],
    run_parallel_tools_fn: Any,
    tool_map: dict[str, Any],
    max_turns: int = MAX_TOOL_TURNS,
    repos: 'Repositories | None' = None,
    llm_chat_fn: Callable[..., Any] | None = None,
    llm_chat_stream_fn: Callable[..., Any] | None = None,
    tool_defs: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[Any, None]:
    """Tool loop for streaming path. Yields NDJSON events."""
    import src.llm.client as llm_client
    import src.tools as tools

    ctx = _ToolLoopContext(
        history=history, model=model, session_id=session_id, tagged=tagged,
        debug=debug, phases_output=phases_output, used_tools=used_tools,
        tool_detail=tool_detail, run_parallel_tools_fn=run_parallel_tools_fn,
        tool_map=tool_map, max_turns=max_turns, repos=repos,
        llm_chat_fn=llm_chat_fn or llm_client.chat,
        llm_chat_stream_fn=llm_chat_stream_fn or llm_client.chat_stream,
        tool_defs=tool_defs or tools.get_default_registry().tools_openai,
    )
    turn = 0
    phase_tool_ids = []
    total_reasoning = []
    prev_content: str | None = None

    while turn < ctx.max_turns:
        reasoning_out: list[Any] = []
        tool_calls_out: list[Any] = []
        accumulated: list[tuple[str, str]] = []
        phase_reasoning = ""

        try:
            async for tipo, token in ctx.llm_chat_stream_fn(
                ctx.history, ctx.model, reasoning_output=reasoning_out, tagged=True,
                tools=ctx.tool_defs, tool_calls_output=tool_calls_out, debug=ctx.debug
            ):
                accumulated.append((tipo, token))
                if tipo == "reasoning":
                    total_reasoning.append(token)
                    phase_reasoning += token
                if ctx.tagged:
                    yield (tipo, token)
                elif tipo == "content":
                    yield token
        except Exception as e:
            logger.error("Error reading from stream: %s", e)
            raise

        curr_content = "".join(t[1] for t in accumulated if t[0] == "content") or None

        if curr_content and prev_content and curr_content == prev_content:
            logger.warning("Duplicate content detected (turn %d), breaking tool loop", turn)
            if phase_reasoning or curr_content:
                _append_phase(ctx.phases_output, phase_reasoning, [], curr_content)
            break

        prev_content = curr_content
        has_tool_call = bool(tool_calls_out)

        if has_tool_call:
            turn += 1
            assistant_content = "".join(t[1] for t in accumulated if t[0] == "content") or None
            async for event in _execute_tools(ctx, turn, phase_tool_ids, tool_calls_out, assistant_content, phase_reasoning):
                yield event
            phase_reasoning = ""
            continue
        else:
            final_content = "".join(t[1] for t in accumulated if t[0] == "content") or ""
            if phase_reasoning or final_content:
                _append_phase(ctx.phases_output, phase_reasoning, [], final_content)
            break

    if ctx.debug is not None:
        ctx.debug.tool_calls = ctx.tool_detail
        ctx.debug.reasoning = "".join(total_reasoning)


async def run_tool_loop_sync(
    history: list[dict[str, Any]],
    model: str,
    session_id: str | None,
    tagged: bool,
    debug: DebugInfo | None,
    phases_output: list[dict[str, Any]] | None,
    used_tools: list[str],
    tool_detail: list[dict[str, Any]],
    run_parallel_tools_fn: Any,
    tool_map: dict[str, Any],
    max_turns: int = MAX_TOOL_TURNS,
    repos: 'Repositories | None' = None,
    llm_chat_fn: Callable[..., Any] | None = None,
    llm_chat_stream_fn: Callable[..., Any] | None = None,
    tool_defs: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[Any, None]:
    """Tool loop for synchronous path (tests). Yields NDJSON events."""
    import src.llm.client as llm_client
    import src.tools as tools

    ctx = _ToolLoopContext(
        history=history, model=model, session_id=session_id, tagged=tagged,
        debug=debug, phases_output=phases_output, used_tools=used_tools,
        tool_detail=tool_detail, run_parallel_tools_fn=run_parallel_tools_fn,
        tool_map=tool_map, max_turns=max_turns, repos=repos,
        llm_chat_fn=llm_chat_fn or llm_client.chat,
        llm_chat_stream_fn=llm_chat_stream_fn or llm_client.chat_stream,
        tool_defs=tool_defs or tools.get_default_registry().tools_openai,
    )
    turn = 0
    phase_reasoning = ""
    phase_tool_ids = []

    result = await ctx.llm_chat_fn(ctx.history, ctx.model, tools=ctx.tool_defs, debug=ctx.debug)
    while result.finish_reason == "tool_calls" and turn < ctx.max_turns:
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
        async for event in _execute_tools(ctx, turn, phase_tool_ids, tool_calls, result.message.content, phase_reasoning):
            yield event

        phase_reasoning = ""
        result = await ctx.llm_chat_fn(ctx.history, ctx.model, tools=ctx.tool_defs)

    if ctx.used_tools:
        logger.info("Using: %s", ", ".join(ctx.used_tools))

    final_reasoning = getattr(result.message, 'reasoning_content', None) or ""
    content_str = ""
    if result.message.content:
        content_str = result.message.content
        if final_reasoning and ctx.tagged:
            yield ("reasoning", final_reasoning)
            _append_phase(ctx.phases_output, final_reasoning, [], content_str)
        for i in range(0, len(content_str), TOOL_OUTPUT_CHUNK_SIZE):
            token = content_str[i:i + TOOL_OUTPUT_CHUNK_SIZE]
            if ctx.tagged:
                yield ("content", token)
            else:
                yield token
    else:
        reasoning_out: list[str] = []
        async for item in ctx.llm_chat_stream_fn(ctx.history, ctx.model, reasoning_output=reasoning_out, tagged=ctx.tagged):
            if ctx.tagged:
                tipo, token = item
                yield (tipo, token)
            else:
                yield item
        final_reasoning = "".join(reasoning_out)

    ctx.history.append(HistoryMessage(
        role="assistant",
        content=content_str,
        tool_calls=[],
        created_at=datetime.now().isoformat()
    ))
    if ctx.session_id and ctx.repos is not None:
        await ctx.repos.messages.save(
            session_id=ctx.session_id,
            role="assistant",
            content=content_str,
            model=ctx.model,
            tool_calls="[]",
        )

    if ctx.debug is not None:
        ctx.debug.tool_calls = ctx.tool_detail
        ctx.debug.reasoning = final_reasoning
