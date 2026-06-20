import json
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from datetime import datetime
from types import SimpleNamespace

from src.core.debug_info import DebugInfo
from src.core.history_contract import HistoryMessage
from src.core.orchestrator_contract import OrchestratorDeps


def _tool_call(tc_id: str, name: str, args: dict[str, object]) -> SimpleNamespace:
    tc = SimpleNamespace()
    tc.id = tc_id
    tc.function = SimpleNamespace()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _make_deps(tool_map=None):
    repos = AsyncMock()
    repos.messages = AsyncMock()
    repos.sessions = AsyncMock()
    repos.tool_calls = AsyncMock()
    repos.widget_states = AsyncMock()
    repos.debug = AsyncMock()
    repos.saved_widgets = AsyncMock()
    repos.memory_index = AsyncMock()
    deps = OrchestratorDeps(repos=repos)
    if tool_map is not None:
        from src.tools.registry import ToolRegistry
        reg = ToolRegistry()
        reg._tool_map = tool_map
        reg._definitions = {}
        reg._built = True
        deps.tool_registry = reg
    return deps


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
async def test_no_tools(mock_chat_stream):
    """Simple text response, no tools needed."""
    async def _stream(messages, model, **kwargs):
        yield ("content", "¡Hola!")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    tokens = [t async for t in chat_stream("Hola!", history, model="test-model", tagged=True, streaming=False, deps=_make_deps())]
    contents = [t for t in tokens if t[0] == "content"]
    full = "".join(t[1] for t in contents)
    assert "¡Hola!" in full
    # Final assistant message appended to history
    assert history[-1].role == "assistant"
    assert history[-1].content == "¡Hola!"
    mock_chat_stream.assert_called_once()


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
@patch("src.tools.get_default_registry")
async def test_tool_call_then_response(mock_get_reg, mock_chat_stream):
    """Model calls a tool, then responds."""
    mock_reg = MagicMock()
    mock_reg.tool_map = {"web_search": AsyncMock(return_value="ok result")}
    mock_reg.tools_openai = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    mock_get_reg.return_value = mock_reg

    call_count = [0]

    async def _stream(messages, model, **kwargs):
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
            yield ("content", "Aquí está la info.")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    debug = DebugInfo()
    
    tokens = [t async for t in chat_stream("Busca algo", history, model="test-model", tagged=True, debug=debug, streaming=False, deps=_make_deps())]

    types_seen = [t[0] for t in tokens]
    assert "reasoning" in types_seen
    assert "tool_call" in types_seen
    assert "content" in types_seen

    # Reasoning from both phases captured
    rcs = [t[1] for t in tokens if t[0] == "reasoning"]
    assert any("I need info" in r for r in rcs)
    assert any("Done thinking" in r for r in rcs)

    # Tool calls yielded
    tcs = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    assert any(t["status"] == "calling" for t in tcs)
    assert any(t["status"] == "ok" for t in tcs)

    # Debug info filled
    assert debug.model == "test-model"
    assert len(debug.tool_calls) >= 1
    assert "Done thinking" in (debug.reasoning or "")


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
@patch("src.tools.get_default_registry")
async def test_tool_error(mock_get_reg, mock_chat_stream):
    """Tool raises an exception."""
    mock_reg = MagicMock()
    async def failing_run(**kwargs):
        raise ValueError("API error")
    mock_reg.tool_map = {"web_search": failing_run}
    mock_reg.tools_openai = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    mock_get_reg.return_value = mock_reg

    call_count = [0]

    async def _stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [_tool_call("c1", "web_search", {"query": "test"})]
        else:
            yield ("content", "Lo siento, hubo un error.")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    
    tokens = [t async for t in chat_stream("test", history, model="test-model", tagged=True, streaming=False, deps=_make_deps())]

    tcs = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    assert any(t["status"] == "error" for t in tcs)


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
@patch("src.tools.get_default_registry")
async def test_session_id_propagates_to_tools(mock_get_reg, mock_chat_stream):
    """session_id is passed as _session_id to tools."""
    mock_reg = MagicMock()
    captured = {}
    async def tracking_tool(**kwargs):
        captured["session_id"] = kwargs.get("_session_id")
        return "ok"
    mock_reg.tool_map = {"web_search": tracking_tool}
    mock_reg.tools_openai = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    mock_get_reg.return_value = mock_reg

    call_count = [0]

    async def _stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [_tool_call("c1", "web_search", {"query": "x"})]
        else:
            yield ("content", "done")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    
    [t async for t in chat_stream("test", history, model="test-model", session_id="ses-123", tagged=True, streaming=False, deps=_make_deps())]

    assert captured.get("session_id") == "ses-123"


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
@patch("src.tools.get_default_registry")
async def test_multiple_tool_calls_same_turn(mock_get_reg, mock_chat_stream):
    """Multiple tools called in a single turn."""
    mock_reg = MagicMock()
    tools_called = []
    async def tracking_tool(**kwargs):
        tools_called.append(kwargs.get("_session_id"))
        return "result"
    mock_reg.tool_map = {"web_search": tracking_tool}
    mock_reg.tools_openai = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    mock_get_reg.return_value = mock_reg

    call_count = [0]

    async def _stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = call_count[0]
        call_count[0] += 1
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [
                    _tool_call("c1", "web_search", {"query": "test1"}),
                    _tool_call("c2", "web_search", {"query": "test2"}),
                    _tool_call("c3", "web_search", {"query": "test3"}),
                ]
        else:
            yield ("content", "Resultados combinados.")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    
    tokens = [t async for t in chat_stream("test", history, model="test-model", session_id="ses-1", tagged=True, streaming=False, deps=_make_deps())]

    tcs = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    calling = [t for t in tcs if t["status"] == "calling"]
    ok = [t for t in tcs if t["status"] == "ok"]
    assert len(calling) == 3
    assert len(ok) == 3
    assert len(tools_called) == 3


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
@patch("src.tools.get_default_registry")
async def test_mixed_tool_results(mock_get_reg, mock_chat_stream):
    """One tool succeeds, one fails in the same turn."""
    mock_reg = MagicMock()
    call_count = [0]
    async def flip_flop(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("fail")
        return "ok result"
    mock_reg.tool_map = {"web_search": flip_flop}
    mock_reg.tools_openai = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    mock_get_reg.return_value = mock_reg

    inner_count = [0]

    async def _stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = inner_count[0]
        inner_count[0] += 1
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [
                    _tool_call("c1", "web_search", {"query": "a"}),
                    _tool_call("c2", "web_search", {"query": "b"}),
                ]
        else:
            yield ("content", "done")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    
    tokens = [t async for t in chat_stream("test", history, model="test-model", session_id="ses-2", tagged=True, streaming=False, deps=_make_deps())]

    tcs = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    errors = [t for t in tcs if t["status"] == "error"]
    oks = [t for t in tcs if t["status"] == "ok"]
    assert len(errors) == 1
    assert len(oks) >= 1


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
@patch("src.tools.get_default_registry")
async def test_tool_result_truncation(mock_get_reg, mock_chat_stream):
    """Tool result >30000 chars gets truncated."""
    mock_reg = MagicMock()
    long_result = "x" * 35000
    mock_reg.tool_map = {"web_search": AsyncMock(return_value=long_result)}
    mock_reg.tools_openai = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    mock_get_reg.return_value = mock_reg

    inner_count = [0]

    async def _stream(messages, model, **kwargs):
        tool_calls_output = kwargs.get("tool_calls_output")
        idx = inner_count[0]
        inner_count[0] += 1
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [_tool_call("c1", "web_search", {"query": "test"})]
        else:
            yield ("content", "done")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    
    [t async for t in chat_stream("test", history, model="test-model", session_id="ses-3", tagged=True, streaming=False, deps=_make_deps())]

    # Check history has truncated tool result
    tool_msgs = [m for m in history if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert len(tool_msgs[0].content) == 30015  # 30000 + "\n...[truncated]"


@pytest.mark.anyio
@patch("src.llm.client.chat_stream")
async def test_empty_message(mock_chat_stream):
    """Empty message still works."""
    async def _stream(messages, model, **kwargs):
        yield ("content", "OK")

    mock_chat_stream.side_effect = _stream
    from src.core.orchestrator import chat_stream

    history = [HistoryMessage(role="system", content="test", created_at=datetime.now().isoformat())]
    tokens = [t async for t in chat_stream("", history, model="test-model", tagged=True, streaming=False, deps=_make_deps())]
    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("OK" in c for c in contents)


@pytest.mark.anyio
@patch("src.core.orchestrator.chat_stream")
async def test_chat_non_streaming(mock_chat_stream):
    """Non-streaming path is just orchestrator.chat_stream(streaming=False)."""
    async def side_effect(message_user, history, **kwargs):
        if not history:
            history.append(HistoryMessage(role="system", content="sys prompt", created_at=datetime.now().isoformat()))
        history.append(HistoryMessage(role="user", content=message_user, created_at=datetime.now().isoformat()))
        msg = HistoryMessage(role="assistant", content="Respuesta de prueba", created_at=datetime.now().isoformat())
        history.append(msg)
        yield "Respuesta de prueba"

    mock_chat_stream.side_effect = side_effect
    from src.core.orchestrator import chat_stream

    history = []
    tokens = [t async for t in chat_stream("Hola", history, model="test-model", streaming=False, deps=_make_deps())]
    assert "Respuesta de prueba" in "".join(tokens)
    assert len(history) >= 2
    assert history[-1].role == "assistant"
    assert history[-1].content == "Respuesta de prueba"
