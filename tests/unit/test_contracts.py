import pytest
from unittest.mock import AsyncMock
import json
from unittest.mock import MagicMock, patch

from src.constants import MAX_TOOL_TURNS, TOOL_OUTPUT_CHUNK_SIZE
from src.config_loader import DEFAULT_CONFIG
from src.core.tool_loop import _ToolLoopContext
from web.services.chat_stream import build_stream_generator


def _bg_tasks():
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


@pytest.mark.anyio
async def test_tool_loop_default_turns_match_shared_constant():
    ctx = _ToolLoopContext(history=[], model="m")
    assert ctx.max_turns == MAX_TOOL_TURNS
    assert MAX_TOOL_TURNS == DEFAULT_CONFIG.max_tool_turns




@pytest.mark.anyio
async def test_tool_runner_heartbeat_constant_is_centralized():
    assert DEFAULT_CONFIG.tool_heartbeat_interval == 10.0


@pytest.mark.anyio
async def test_tool_output_chunk_size_is_shared():
    assert TOOL_OUTPUT_CHUNK_SIZE == 12


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
@pytest.mark.anyio
async def test_stream_contract_uses_ndjson_t_and_d(mock_chat_stream, mock_save):
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

    mock_chat_stream.return_value = _AsyncIter([
        ("reasoning", "Pensando"),
        ("content", "Hola"),
    ])

    gen = build_stream_generator(
        "ses-contract",
        "Hola",
        [{"role": "system", "content": "test"}],
        "test-model",
        _bg_tasks(),
    )
    chunks = [chunk async for chunk in gen()]

    assert chunks
    parsed = [json.loads(chunk.strip()) for chunk in chunks]
    assert parsed[0]["t"] == "reasoning"
    assert parsed[0]["d"] == "Pensando"
    assert parsed[1]["t"] == "content"
    assert parsed[1]["d"] == "Hola"
    assert all(sorted(item.keys()) == ["d", "t"] for item in parsed)
    mock_save.assert_called_once()
