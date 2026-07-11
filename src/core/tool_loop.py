import logging
import json
from collections.abc import AsyncGenerator, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.constants import max_tool_turns
from src.memory.types import DebugInfo
from src.memory.repos import Repositories
from src.core.history_contract import HistoryMessage

logger = logging.getLogger(__name__)


@runtime_checkable
class ToolLoopProtocol(Protocol):
    """Protocol for tool loop functions (run_tool_loop_streaming / run_tool_loop_sync)."""
    async def __call__(
        self,
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
        max_turns: int = ...,
        repos: 'Repositories | None' = ...,
        llm_chat_fn: Callable[..., Any] | None = ...,
        llm_chat_stream_fn: Callable[..., Any] | None = ...,
        tool_defs: list[dict[str, Any]] | None = ...,
        skill_registry: Any | None = ...,
    ) -> AsyncGenerator[Any, None]: ...


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
    max_turns: int = field(default_factory=max_tool_turns)
    llm_chat_fn: Callable[..., Any] | None = None
    llm_chat_stream_fn: Callable[..., Any] | None = None
    tool_defs: list[dict[str, Any]] | None = None
    skill_registry: Any | None = None


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _build_ctx(
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
    max_turns: int,
    repos: 'Repositories | None',
    llm_chat_fn: Callable[..., Any] | None,
    llm_chat_stream_fn: Callable[..., Any] | None,
    tool_defs: list[dict[str, Any]] | None,
    skill_registry: Any | None = None,
) -> _ToolLoopContext:
    import src.llm.client as llm_client
    import src.tools as tools

    return _ToolLoopContext(
        history=history, model=model, session_id=session_id, tagged=tagged,
        debug=debug, phases_output=phases_output, used_tools=used_tools,
        tool_detail=tool_detail, run_parallel_tools_fn=run_parallel_tools_fn,
        tool_map=tool_map, max_turns=max_turns, repos=repos,
        llm_chat_fn=llm_chat_fn or llm_client.chat,
        llm_chat_stream_fn=llm_chat_stream_fn or llm_client.chat_stream,
        tool_defs=tool_defs or tools.get_default_registry().tools_openai,
        skill_registry=skill_registry,
    )


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


def _set_debug(ctx: _ToolLoopContext, reasoning: str) -> None:
    if ctx.debug is not None:
        ctx.debug.tool_calls = ctx.tool_detail
        ctx.debug.reasoning = reasoning


# â”€â”€ tool execution (shared) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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
        repos=ctx.repos, skill_registry=ctx.skill_registry,
    ):
        yield event

    _append_phase(ctx.phases_output, reasoning, list(phase_tool_ids), content or "")
    phase_tool_ids.clear()


# â”€â”€ core streaming loop (internal, unifies yielÔ mechanism) â”€â”€â”€â”€â”€â”€


async def _run_tool_loop(
    ctx: _ToolLoopContext,
    *,
    yield_event: Callable[[Any], Awaitable[None]] | None = None,
) -> AsyncGenerator[Any, None]:
    """Core streaming tool loop.

    Yields events directly. When *yield_event* is provided, each event
    is also dispatched through the callback instead of (or in addition
    to) the generator yield â€” this lets the sync path intercept events
    without changing the loop structure.
    """
    turn = 0
    phase_tool_ids: list[str] = []
    total_reasoning: list[str] = []
    prev_content: str | None = None

    while turn < ctx.max_turns:
        reasoning_out: list[Any] = []
        tool_calls_out: list[Any] = []
        accumulated: list[tuple[str, str]] = []
        phase_reasoning = ""

        try:
            async for tipo, token in ctx.llm_chat_stream_fn(
                ctx.history, ctx.model, reasoning_output=reasoning_out, tagged=True,
                tools=ctx.tool_defs, tool_calls_output=tool_calls_out, debug=ctx.debug,
            ):
                accumulated.append((tipo, token))
                if tipo == "reasoning":
                    total_reasoning.append(token)
                    phase_reasoning += token
                if ctx.tagged:
                    if yield_event:
                        await yield_event((tipo, token))
                    yield (tipo, token)
                elif tipo == "content":
                    if yield_event:
                        await yield_event(token)
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

        if tool_calls_out:
            turn += 1
            assistant_content = "".join(t[1] for t in accumulated if t[0] == "content") or None
            async for event in _execute_tools(ctx, turn, phase_tool_ids, tool_calls_out, assistant_content, phase_reasoning):
                if yield_event:
                    await yield_event(event)
                yield event
            phase_reasoning = ""
            continue

        final_content = "".join(t[1] for t in accumulated if t[0] == "content") or ""
        if phase_reasoning or final_content:
            _append_phase(ctx.phases_output, phase_reasoning, [], final_content)
        break

    _set_debug(ctx, "".join(total_reasoning))


# â”€â”€ public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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
    max_turns: int | None = None,
    repos: 'Repositories | None' = None,
    llm_chat_fn: Callable[..., Any] | None = None,
    llm_chat_stream_fn: Callable[..., Any] | None = None,
    tool_defs: list[dict[str, Any]] | None = None,
    skill_registry: Any | None = None,
) -> AsyncGenerator[Any, None]:
    """Tool loop for streaming path. Yields NDJSON events."""
    ctx = _build_ctx(
        history, model, session_id, tagged, debug, phases_output,
        used_tools, tool_detail, run_parallel_tools_fn, tool_map,
        max_turns if max_turns is not None else max_tool_turns(),
        repos, llm_chat_fn, llm_chat_stream_fn, tool_defs,
        skill_registry=skill_registry,
    )
    async for event in _run_tool_loop(ctx):
        yield event


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
    max_turns: int | None = None,
    repos: 'Repositories | None' = None,
    llm_chat_fn: Callable[..., Any] | None = None,
    llm_chat_stream_fn: Callable[..., Any] | None = None,
    tool_defs: list[dict[str, Any]] | None = None,
    skill_registry: Any | None = None,
) -> AsyncGenerator[Any, None]:
    """Tool loop for synchronous path (tests). Yields NDJSON events.

    Delegates to the shared streaming loop (``_run_tool_loop``) and adds
    sync-specific post-processing: final assistant message persistence and
    *used_tools* logging.

    ``max_turns`` is interpreted as the maximum number of *tool-call* turns -
    one extra LLM call is made for the final assistant response.
    """
    ctx = _build_ctx(
        history, model, session_id, tagged, debug, phases_output,
        used_tools, tool_detail, run_parallel_tools_fn, tool_map,
        (max_turns if max_turns is not None else max_tool_turns()) + 1,
        repos, llm_chat_fn, llm_chat_stream_fn, tool_defs,
        skill_registry=skill_registry,
    )

    async for event in _run_tool_loop(ctx):
        yield event

    if ctx.used_tools:
        logger.info("Using: %s", ", ".join(ctx.used_tools))

    final_content = ""
    if ctx.phases_output:
        last_phase = ctx.phases_output[-1]
        final_content = last_phase.get("content", "") or ""

    ctx.history.append(HistoryMessage(
        role="assistant",
        content=final_content or None,
        tool_calls=[],
        created_at=datetime.now().isoformat()
    ))
    if ctx.session_id and ctx.repos is not None:
        await ctx.repos.messages.save(
            session_id=ctx.session_id,
            role="assistant",
            content=final_content or None,
            model=ctx.model,
            tool_calls="[]",
        )
