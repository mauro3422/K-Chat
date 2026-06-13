import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from src.core.debug_info import DebugInfo


# ---------------------------------------------------------------------------
# _save_debug_info tests
# ---------------------------------------------------------------------------

def test_save_debug_info_debug_is_none():
    from src.core.orchestrator import _save_debug_info
    _save_debug_info(None, [{"role": "user", "content": "hi"}], None)


def test_save_debug_info_sets_history_before():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    _save_debug_info(debug, history, None)
    assert len(debug.history_before) == 2
    assert debug.history_before[0]["role"] == "user"
    assert debug.history_before[0]["content"] == "hello"
    assert debug.phases == "[]"


def test_save_debug_info_with_phases():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    phases = [{"reasoning": "thinking...", "tool_ids": [], "content": "result"}]
    _save_debug_info(debug, [], phases)
    assert debug.phases == json.dumps(phases)


def test_save_debug_info_phases_none():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    _save_debug_info(debug, [], None)
    assert debug.phases == "[]"


def test_save_debug_info_truncates_content():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    long = "x" * 1000
    history = [{"role": "user", "content": long}]
    _save_debug_info(debug, history, None)
    assert len(debug.history_before[0]["content"]) == 500


# ---------------------------------------------------------------------------
# _compress_if_needed tests
# ---------------------------------------------------------------------------

def test_compress_if_needed_below_threshold():
    from src.core.orchestrator import _compress_if_needed
    history = [{"role": "user", "content": "hello"}]
    mock_should = MagicMock(return_value=False)
    mock_compress = MagicMock()
    _compress_if_needed(history, "test-model", compress_fn=mock_compress, should_compress_fn=mock_should)
    mock_should.assert_called_once_with(history)
    mock_compress.assert_not_called()


def test_compress_if_needed_above_threshold():
    from src.core.orchestrator import _compress_if_needed
    history = [{"role": "user", "content": "hello"}]
    mock_should = MagicMock(return_value=True)
    mock_compress = MagicMock()
    _compress_if_needed(history, "test-model", compress_fn=mock_compress, should_compress_fn=mock_should)
    mock_compress.assert_called_once_with(history, "test-model")


def test_compress_if_needed_error(caplog):
    from src.core.orchestrator import _compress_if_needed
    mock_should = MagicMock(return_value=True)
    mock_compress = MagicMock(side_effect=ValueError("compress failed"))
    with caplog.at_level(logging.WARNING):
        _compress_if_needed([{"role": "user", "content": "hello"}], "test-model",
                            compress_fn=mock_compress, should_compress_fn=mock_should)
    assert "compress_history failed" in caplog.text


# ---------------------------------------------------------------------------
# chat_stream tests
# ---------------------------------------------------------------------------

@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_content_only(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    mock_loop_stream.return_value = iter([
        ("reasoning", "thinking..."),
        ("content", "hello world"),
    ])
    from src.core.orchestrator import chat_stream

    history = [{"role": "system", "content": "test"}]
    tokens = list(chat_stream("hello", history, model="test-model",
                               tagged=True, streaming=True))
    types = [t[0] for t in tokens]
    assert "reasoning" in types
    assert "content" in types
    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("hello world" in c for c in contents)
    assert history[-1] == {"role": "user", "content": "hello"}
    mock_build_sp.assert_not_called()
    mock_get_model.assert_not_called()
    mock_compress.assert_called_once()
    mock_save_debug.assert_called_once()


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_untagged(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    mock_loop_stream.return_value = iter(["raw content"])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = list(chat_stream("hi", history, model="m",
                               tagged=False, streaming=True))
    assert tokens == ["raw content"]


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_default_model(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    mock_get_model.return_value = "default-model"
    mock_loop_stream.return_value = iter([])
    from src.core.orchestrator import chat_stream
    list(chat_stream("hi", [{"role": "system", "content": "test"}],
                      streaming=True))
    mock_get_model.assert_called_once()
    assert mock_loop_stream.call_args[0][1] == "default-model"


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_empty_history(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    mock_build_sp.return_value = {"role": "system", "content": "sys prompt"}
    mock_loop_stream.return_value = iter([])
    from src.core.orchestrator import chat_stream
    history = []
    list(chat_stream("hi", history, model="m", streaming=True))
    assert history[0] == {"role": "system", "content": "sys prompt"}
    mock_build_sp.assert_called_once_with("m")


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_debug_setup(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    mock_loop_stream.return_value = iter([])
    from src.core.orchestrator import chat_stream
    debug = DebugInfo()
    history = [{"role": "system", "content": "test"}]
    list(chat_stream("hi", history, model="m", session_id="sess-1",
                      debug=debug, tagged=True, streaming=True))
    assert debug.model == "m"
    assert debug.session_id == "sess-1"
    assert debug.reasoning == ""
    assert debug.tool_calls == []
    assert debug.system_prompt == "test"
    assert len(debug.history_before) == 2
    assert debug.history_before[1]["content"] == "hi"


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_phases_output_cleared(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    phases = [{"old": "data"}]
    mock_loop_stream.return_value = iter([])
    from src.core.orchestrator import chat_stream
    list(chat_stream("hi", [{"role": "system", "content": "t"}],
                      model="m", debug=DebugInfo(), phases_output=phases,
                      tagged=True, streaming=True))
    assert phases == []


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_sync")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_sync_path(
    mock_get_model, mock_build_sp, mock_loop_stream, mock_loop_sync,
    mock_compress, mock_save_debug,
):
    mock_loop_sync.return_value = iter([("content", "sync result")])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = list(chat_stream("hi", history, model="m",
                               tagged=True, streaming=False))
    mock_loop_stream.assert_not_called()
    mock_loop_sync.assert_called_once()
    assert any(t == ("content", "sync result") for t in tokens)


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_tool_calls(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    tc1 = json.dumps({"name": "web_search", "args": {"q": "test"}, "status": "calling"})
    tc2 = json.dumps({"name": "web_search", "args": {"q": "test"}, "status": "ok", "result": "found"})
    mock_loop_stream.return_value = iter([
        ("tool_call", tc1),
        ("tool_call", tc2),
        ("content", "here you go"),
    ])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = list(chat_stream("search", history, model="m",
                               tagged=True, streaming=True))
    types = [t[0] for t in tokens]
    assert "tool_call" in types
    assert "content" in types
    tool_events = [t[1] for t in tokens if t[0] == "tool_call"]
    assert any("calling" in te for te in tool_events)
    assert any("ok" in te for te in tool_events)


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator.run_tool_loop_streaming")
@patch("src.core.orchestrator.build_system_prompt")
@patch("src.llm.selector.get_default_model")
def test_chat_stream_loop_error_propagates(
    mock_get_model, mock_build_sp, mock_loop_stream,
    mock_compress, mock_save_debug,
):
    mock_loop_stream.side_effect = RuntimeError("stream failure")
    from src.core.orchestrator import chat_stream
    with pytest.raises(RuntimeError, match="stream failure"):
        list(chat_stream("hi", [{"role": "system", "content": "t"}],
                          model="m", streaming=True))
    mock_save_debug.assert_not_called()
    mock_compress.assert_not_called()
