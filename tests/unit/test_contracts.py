import json
from unittest.mock import MagicMock, patch

from src.constants import MAX_TOOL_TURNS, TOOL_HEARTBEAT_INTERVAL
from src.core.tool_loop import _ToolLoopContext
from web.services.chat_stream import build_stream_generator


def _bg_tasks():
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


def test_tool_loop_default_turns_match_shared_constant():
    ctx = _ToolLoopContext(history=[], model="m")
    assert ctx.max_turns == MAX_TOOL_TURNS
    assert MAX_TOOL_TURNS == 25




def test_tool_runner_heartbeat_constant_is_centralized():
    assert TOOL_HEARTBEAT_INTERVAL == 10.0


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
def test_stream_contract_uses_ndjson_t_and_d(mock_chat_stream, mock_save):
    mock_chat_stream.return_value = iter([
        ("reasoning", "Pensando"),
        ("content", "Hola"),
    ])

    chunks = list(build_stream_generator(
        "ses-contract",
        "Hola",
        [{"role": "system", "content": "test"}],
        "test-model",
        _bg_tasks(),
    )())

    assert chunks
    parsed = [json.loads(chunk.strip()) for chunk in chunks]
    assert parsed[0]["t"] == "reasoning"
    assert parsed[0]["d"] == "Pensando"
    assert parsed[1]["t"] == "content"
    assert parsed[1]["d"] == "Hola"
    assert all(sorted(item.keys()) == ["d", "t"] for item in parsed)
    mock_save.assert_called_once()
