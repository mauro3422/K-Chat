import pytest
from unittest.mock import AsyncMock
import json
from unittest.mock import patch, MagicMock

from src.constants import TOOL_OUTPUT_CHUNK_SIZE
from src.core.debug_info import DebugInfo
from src.core.tool_loop import run_tool_loop_sync


def _make_result(content=None, finish_reason="stop", tool_calls=None, reasoning_content=None):
    msg = MagicMock()
    msg.content = content
    msg.reasoning_content = reasoning_content
    if tool_calls:
        tcs = []
        for tc in tool_calls:
            mock_tc = MagicMock()
            mock_tc.id = tc.get("id", "call_1")
            mock_tc.function.name = tc["name"]
            mock_tc.function.arguments = json.dumps(tc.get("args", {}))
            tcs.append(mock_tc)
        msg.tool_calls = tcs
    else:
        msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    return choice


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


@patch("src.llm.client.chat")
@pytest.mark.anyio
async def test_sync_no_tool_calls_tagged(mock_chat):
    content = "Hello world! This is a test."
    mock_chat.return_value = _make_result(
        content=content,
        finish_reason="stop",
        reasoning_content="I am thinking...",
    )

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
    )
    tokens = await _collect_async(gen)

    types = [t[0] for t in tokens]
    assert "reasoning" in types
    assert "content" in types

    reasoning_tokens = [t[1] for t in tokens if t[0] == "reasoning"]
    assert any("I am thinking..." in r for r in reasoning_tokens)

    content_tokens = [t[1] for t in tokens if t[0] == "content"]
    full = "".join(content_tokens)
    assert full == content

    for i, ct in enumerate(content_tokens[:-1]):
        assert len(ct) == TOOL_OUTPUT_CHUNK_SIZE, f"chunk {i} len={len(ct)}: {ct!r}"

    mock_chat.assert_called_once()


@patch("src.llm.client.chat")
@pytest.mark.anyio
async def test_sync_no_tool_calls_untagged(mock_chat):
    content = "Hello world! This is a test."
    mock_chat.return_value = _make_result(
        content=content,
        finish_reason="stop",
    )

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=False, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
    )
    tokens = await _collect_async(gen)

    assert all(isinstance(t, str) for t in tokens)
    assert "".join(tokens) == content
    mock_chat.assert_called_once()


@patch("src.llm.client.chat")
@pytest.mark.anyio
async def test_sync_tool_calls_then_response(mock_chat):
    mock_chat.side_effect = [
        _make_result(
            content="Let me search...",
            finish_reason="tool_calls",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "test"}}],
            reasoning_content="I need info",
        ),
        _make_result(
            content="Here is the result.",
            finish_reason="stop",
            reasoning_content="Done thinking",
        ),
    ]

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
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

    assert mock_chat.call_count == 2


@patch("src.llm.client.chat")
@pytest.mark.anyio
async def test_sync_max_turns(mock_chat):
    mock_chat.side_effect = [
        _make_result(
            finish_reason="tool_calls",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "x"}}],
        ),
        _make_result(
            finish_reason="tool_calls",
            tool_calls=[{"id": "c2", "name": "web_search", "args": {"query": "x"}}],
        ),
        _make_result(
            content="Final.",
            finish_reason="stop",
        ),
    ]

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=False, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=2,
    )
    tokens = await _collect_async(gen)

    assert mock_chat.call_count == 3
    assert "Final." in "".join(tokens)


@patch("src.llm.client.chat")
@pytest.mark.anyio
async def test_sync_session_id_none(mock_chat):
    mock_chat.return_value = _make_result(content="No session.", finish_reason="stop")

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
    )
    tokens = await _collect_async(gen)

    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("No session." in c for c in contents)
    mock_chat.assert_called_once()


@patch("src.llm.client.chat")
@pytest.mark.anyio
async def test_sync_debug_dict(mock_chat):
    mock_chat.side_effect = [
        _make_result(
            finish_reason="tool_calls",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "x"}}],
            reasoning_content="Searching...",
        ),
        _make_result(
            content="Found it.",
            finish_reason="stop",
            reasoning_content="Done.",
        ),
    ]

    history = [{"role": "system", "content": "test"}]
    debug = DebugInfo()
    tool_detail = []
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=debug, phases_output=None,
        used_tools=[], tool_detail=tool_detail,
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
    )
    await _collect_async(gen)

    assert debug.tool_calls is tool_detail
    assert "Done." in debug.reasoning


@patch("src.llm.client.chat")
@patch("src.llm.client.chat_stream")
@pytest.mark.anyio
async def test_sync_empty_content_falls_to_stream(mock_stream, mock_chat):
    mock_chat.return_value = _make_result(content=None, finish_reason="stop")

    class _AsyncIter:
        def __init__(self, items):
            self._items = list(items)
            self._idx = 0
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self._idx >= len(self._items):
                raise StopAsyncIteration
            item = self._items[self._idx]
            self._idx += 1
            return item

    mock_stream.return_value = _AsyncIter([
        ("reasoning", "Stream reasoning..."),
        ("content", "Stream content."),
    ])

    history = [{"role": "system", "content": "test"}]
    gen = run_tool_loop_sync(
        history=history, model="test-model", session_id=None,
        tagged=True, debug=None, phases_output=None,
        used_tools=[], tool_detail=[],
        run_parallel_tools_fn=_empty_generator,
        tool_map={}, max_turns=5,
    )
    tokens = await _collect_async(gen)

    types = [t[0] for t in tokens]
    assert "reasoning" in types
    assert "content" in types

    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("Stream content." in c for c in contents)

    mock_stream.assert_called_once()
    mock_chat.assert_called_once()
