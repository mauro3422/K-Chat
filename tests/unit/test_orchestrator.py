import json
import logging
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.core.debug_info import DebugInfo
from src.core.history_contract import HistoryMessage

async def async_iter(items):
    for item in items:
        yield item

# ---------------------------------------------------------------------------
# _save_debug_info tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_save_debug_info_debug_is_none():
    from src.core.orchestrator import _save_debug_info
    _save_debug_info(None, [{"role": "user", "content": "hi"}], None)


@pytest.mark.anyio
async def test_save_debug_info_sets_history_before():
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


@pytest.mark.anyio
async def test_save_debug_info_with_phases():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    phases = [{"reasoning": "thinking...", "tool_ids": [], "content": "result"}]
    _save_debug_info(debug, [], phases)
    assert debug.phases == json.dumps(phases)


@pytest.mark.anyio
async def test_save_debug_info_phases_none():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    _save_debug_info(debug, [], None)
    assert debug.phases == "[]"


@pytest.mark.anyio
async def test_save_debug_info_truncates_content():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    long = "x" * 1000
    history = [{"role": "user", "content": long}]
    _save_debug_info(debug, history, None)
    assert len(debug.history_before[0]["content"]) == 500


# ---------------------------------------------------------------------------
# compress_if_needed tests (Moved to HistoryService)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_compress_if_needed_below_threshold():
    from src.core.services.history_service import HistoryService
    service = HistoryService()
    history = [{"role": "user", "content": "hello"}]
    mock_should = MagicMock(return_value=False)
    mock_compress = AsyncMock()
    await service.compress_if_needed(history, "test-model", compress_fn=mock_compress, should_compress_fn=mock_should)
    mock_should.assert_called_once_with(history)
    mock_compress.assert_not_called()


@pytest.mark.anyio
async def test_compress_if_needed_above_threshold():
    from src.core.services.history_service import HistoryService
    service = HistoryService()
    history = [{"role": "user", "content": "hello"}]
    mock_should = MagicMock(return_value=True)
    mock_compress = AsyncMock()
    await service.compress_if_needed(history, "test-model", compress_fn=mock_compress, should_compress_fn=mock_should)
    mock_compress.assert_called_once_with(history, "test-model")


@pytest.mark.anyio
async def test_compress_if_needed_error(caplog):
    from src.core.services.history_service import HistoryService
    service = HistoryService()
    mock_should = MagicMock(return_value=True)
    mock_compress = AsyncMock(side_effect=ValueError("compress failed"))
    with caplog.at_level(logging.WARNING):
        await service.compress_if_needed([{"role": "user", "content": "hello"}], "test-model",
                                          compress_fn=mock_compress, should_compress_fn=mock_should)
    assert "compress_history failed" in caplog.text


# ---------------------------------------------------------------------------
# chat_stream tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_content_only(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter([
        ("reasoning", "thinking..."),
        ("content", "hello world"),
    ])
    from src.core.orchestrator import chat_stream

    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("hello", history, model="test-model", tagged=True, streaming=True):
        tokens.append(t)
        
    types = [t[0] for t in tokens]
    assert "reasoning" in types
    assert "content" in types
    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("hello world" in c for c in contents)
    assert history[-1].role == "user"
    assert history[-1].content == "hello"
    mock_get_sp.assert_not_called()
    mock_get_model.assert_not_called()
    mock_compress.assert_called_once()
    mock_save_debug.assert_called_once()


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_untagged(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter(["raw content"])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("hi", history, model="m", tagged=False, streaming=True):
        tokens.append(t)
    assert tokens == ["raw content"]


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_default_model(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_get_model.return_value = "default-model"
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    async for _ in chat_stream("hi", [{"role": "system", "content": "test"}], streaming=True):
        pass
    mock_get_model.assert_called_once()
    assert mock_execute.call_args[0][1] == "default-model"


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_empty_history(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_get_sp.return_value = {"role": "system", "content": "sys prompt"}
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    history = []
    async for _ in chat_stream("hi", history, model="m", streaming=True):
        pass
    assert history[0].role == "system"
    assert history[0].content == "sys prompt"
    mock_get_sp.assert_called_once_with("m")


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_debug_setup(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    debug = DebugInfo()
    history = [HistoryMessage(role="system", content="test", created_at="2024-01-01T00:00:00")]
    async for _ in chat_stream("hi", history, model="m", session_id="sess-1",
                                debug=debug, tagged=True, streaming=True):
        pass
    assert debug.model == "m"
    assert debug.session_id == "sess-1"
    assert debug.reasoning == ""
    assert debug.tool_calls == []
    assert debug.system_prompt == "test"
    assert len(debug.history_before) == 2
    assert debug.history_before[1]["content"] == "hi"


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_phases_output_cleared(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    phases = [{"old": "data"}]
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    async for _ in chat_stream("hi", [{"role": "system", "content": "t"}],
                                model="m", debug=DebugInfo(), phases_output=phases,
                                tagged=True, streaming=True):
        pass
    assert phases == []


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_sync_path(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter([("content", "sync result")])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("hi", history, model="m", tagged=True, streaming=False):
        tokens.append(t)
    mock_execute.assert_called_once()
    assert any(t == ("content", "sync result") for t in tokens)


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_tool_calls(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    tc1 = json.dumps({"name": "web_search", "args": {"q": "test"}, "status": "calling"})
    tc2 = json.dumps({"name": "web_search", "args": {"q": "test"}, "status": "ok", "result": "found"})
    mock_execute.return_value = async_iter([
        ("tool_call", tc1),
        ("tool_call", tc2),
        ("content", "here you go"),
    ])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("search", history, model="m", tagged=True, streaming=True):
        tokens.append(t)
    types = [t[0] for t in tokens]
    assert "tool_call" in types
    assert "content" in types
    tool_events = [t[1] for t in tokens if t[0] == "tool_call"]
    assert any("calling" in te for te in tool_events)
    assert any("ok" in te for te in tool_events)


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_loop_error_propagates(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.side_effect = RuntimeError("stream failure")
    from src.core.orchestrator import chat_stream
    with pytest.raises(RuntimeError, match="stream failure"):
        async for _ in chat_stream("hi", [{"role": "system", "content": "t"}], model="m", streaming=True):
            pass
    mock_save_debug.assert_not_called()
    mock_compress.assert_not_called()
