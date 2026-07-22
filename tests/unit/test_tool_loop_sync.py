import pytest
from unittest.mock import AsyncMock
import json
from types import SimpleNamespace

from src.core.debug_info import DebugInfo
from src.core.tool_loop import run_tool_loop_sync


def _tool_call(tc_id: str, name: str, args: dict[str, object]) -> SimpleNamespace:
    tc = SimpleNamespace()
    tc.id = tc_id
    tc.function = SimpleNamespace()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


class _EmptyAsyncIter:
    def __aiter__(self):
        return self
    async def __anext__(self):
        raise StopAsyncIteration


def _empty_generator(*args, **kwargs):
    return _EmptyAsyncIter()


async def _collect_async(gen):
    items = []
    async for item in gen:
        items.append(item)
    return items


@pytest.mark.anyio
async def test_sync_no_tool_calls_tagged():
    async def llm_stream(messages, model, **kwargs):
        yield ("reasoning", "I am thinking...")
        yield ("content", "Hello world! This is a test.")

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
        llm_chat_stream_fn=llm_stream,
    )
    tokens = await _collect_async(gen)

    types = [t[0] for t in tokens]
    assert "reasoning" in types
    assert "content" in types
    assert ("checkpoint", {"kind": "final_phase"}) in tokens

    reasoning_tokens = [t[1] for t in tokens if t[0] == "reasoning"]
    assert any("I am thinking..." in r for r in reasoning_tokens)

    content_tokens = [t[1] for t in tokens if t[0] == "content"]
    full = "".join(content_tokens)
    assert full == "Hello world! This is a test."


@pytest.mark.anyio
async def test_sync_no_tool_calls_untagged():
    async def llm_stream(messages, model, **kwargs):
        yield ("content", "Hello world! This is a test.")

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=False, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
        llm_chat_stream_fn=llm_stream,
    )
    tokens = await _collect_async(gen)

    assert all(isinstance(t, str) for t in tokens)
    assert "".join(tokens) == "Hello world! This is a test."


@pytest.mark.anyio
async def test_sync_tool_calls_then_response():
    call_count = [0]

    async def llm_stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [_tool_call("c1", "web_search", {"query": "test"})]
            yield ("reasoning", "I need info")
            yield ("content", "Let me search...")
        else:
            yield ("reasoning", "Done thinking")
            yield ("content", "Here is the result.")

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
        llm_chat_stream_fn=llm_stream,
    )
    tokens = await _collect_async(gen)

    types = [t[0] for t in tokens]
    assert "reasoning" in types
    assert "content" in types

    reasoning_tokens = [t[1] for t in tokens if t[0] == "reasoning"]
    assert any("I need info" in r for r in reasoning_tokens)
    assert any("Done thinking" in r for r in reasoning_tokens)

    contents = "".join(t[1] for t in tokens if t[0] == "content")
    assert "Here is the result." in contents


@pytest.mark.anyio
async def test_sync_max_turns():
    call_count = [0]

    async def llm_stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = call_count[0]
        call_count[0] += 1
        if idx < 2:
            if tool_calls_output is not None:
                tool_calls_output[:] = [_tool_call(f"c{idx + 1}", "web_search", {"query": "x"})]
        else:
            yield ("content", "Final.")

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=False, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=2,
        llm_chat_stream_fn=llm_stream,
    )
    tokens = await _collect_async(gen)

    assert call_count[0] == 3
    assert "Final." in "".join(tokens)


@pytest.mark.anyio
async def test_sync_session_id_none():
    async def llm_stream(messages, model, **kwargs):
        yield ("content", "No session.")

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
        llm_chat_stream_fn=llm_stream,
    )
    tokens = await _collect_async(gen)

    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("No session." in c for c in contents)


@pytest.mark.anyio
async def test_sync_debug_dict():
    call_count = [0]

    async def llm_stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [_tool_call("c1", "web_search", {"query": "x"})]
            yield ("reasoning", "Searching...")
        else:
            yield ("reasoning", "Done.")
            yield ("content", "Found it.")

    history = [{"role": "system", "content": "test"}]
    debug = DebugInfo()
    tool_detail = []
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=debug, phases_output=None,
        used_tools=[], tool_detail=tool_detail,
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
        llm_chat_stream_fn=llm_stream,
    )
    await _collect_async(gen)

    assert debug.tool_calls is tool_detail
    assert "Done." in debug.reasoning
