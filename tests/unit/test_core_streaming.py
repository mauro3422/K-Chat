import json
import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

from src.core.orchestrator_contract import OrchestratorDeps
from src.tools.registry import ToolRegistry


async def _stream_events(events):
    for e in events:
        yield e


def _make_stream_mock(events_by_call, tool_calls_by_call=None):
    if tool_calls_by_call is None:
        tool_calls_by_call = [None] * len(events_by_call)

    def factory(*args, **kwargs):
        call_idx = factory.call_count
        factory.call_count += 1

        tco = kwargs.get("tool_calls_output")
        tcs = tool_calls_by_call[call_idx] if call_idx < len(tool_calls_by_call) else None
        if tcs is not None and tco is not None:
            tco[:] = tcs

        events = events_by_call[call_idx] if call_idx < len(events_by_call) else []

        async def gen():
            for e in events:
                yield e

        return gen()

    factory.call_count = 0
    return factory


def _make_tool_call_obj(name: str, args: dict, tc_id: str = "call_1"):
    tc = SimpleNamespace()
    tc.id = tc_id
    tc.function = SimpleNamespace()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _make_deps(tool_map):
    reg = ToolRegistry()
    reg._tool_map = tool_map
    reg._definitions = {}
    reg._built = True
    repos = MagicMock()
    repos.messages.save = AsyncMock()
    repos.tool_calls.record_execution = AsyncMock()
    deps = OrchestratorDeps(repos=repos)
    deps.tool_registry = reg
    return deps


@pytest.mark.anyio
@patch("src.llm.client.chat", new_callable=AsyncMock)
@patch("src.llm.client.chat_stream")
async def test_streaming_content_only(mock_stream, mock_chat):
    from src.core.orchestrator import chat_stream

    mock_stream.side_effect = _make_stream_mock([
        [("reasoning", "pensando..."), ("content", "Hola mundo")],
    ])

    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("Hola", history, model="test-model", tagged=True, streaming=True, deps=_make_deps({})):
        tokens.append(t)

    types = [t[0] for t in tokens]
    texts = [t[1] for t in tokens if t[0] == "content"]
    assert "reasoning" in types
    assert "content" in types
    assert any("Hola mundo" in t for t in texts)
    mock_chat.assert_not_called()


@pytest.mark.anyio
@patch("src.llm.client.chat", new_callable=AsyncMock)
@patch("src.llm.client.chat_stream")
async def test_streaming_tool_then_content(mock_stream, mock_chat):
    from src.core.orchestrator import chat_stream

    tcs = [_make_tool_call_obj("web_search", {"query": "test"}, "c1")]
    mock_stream.side_effect = _make_stream_mock(
        [
            [("tool_call", json.dumps({"name": "web_search", "args": {}, "status": "calling"}))],
            [("reasoning", "Done thinking"), ("content", "Resultado final.")],
        ],
        tool_calls_by_call=[tcs, None],
    )

    async def mock_tool(**kw):
        return "ok result"

    deps = _make_deps({"web_search": mock_tool})

    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("Busca", history, model="test-model", tagged=True, streaming=True, deps=deps):
        tokens.append(t)

    types = [t[0] for t in tokens]
    assert "reasoning" in types, f"Falta reasoning, types={types}"
    assert "tool_call" in types, f"Falta tool_call, types={types}"
    assert "content" in types, f"Falta content, types={types}"

    tcs_events = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    assert any(t["status"] == "calling" for t in tcs_events)
    assert any(t["status"] == "ok" for t in tcs_events)

    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("Resultado final" in c for c in contents)

    tool_msgs = [m for m in history if (m["role"] if isinstance(m, dict) else m.role) == "tool"]
    assert len(tool_msgs) == 1
    content = tool_msgs[0]["content"] if isinstance(tool_msgs[0], dict) else tool_msgs[0].content
    assert "ok result" in content

    mock_chat.assert_not_called()


@pytest.mark.anyio
@patch("src.llm.client.chat", new_callable=AsyncMock)
@patch("src.llm.client.chat_stream")
async def test_streaming_multiple_tools(mock_stream, mock_chat):
    from src.core.orchestrator import chat_stream

    tcs = [
        _make_tool_call_obj("web_search", {"query": "a"}, "c1"),
        _make_tool_call_obj("web_search", {"query": "b"}, "c2"),
        _make_tool_call_obj("web_search", {"query": "c"}, "c3"),
    ]
    mock_stream.side_effect = _make_stream_mock(
        [
            [("tool_call", json.dumps({"name": "web_search", "args": {}, "status": "calling"}))],
            [("content", "Hecho.")],
        ],
        tool_calls_by_call=[tcs, None],
    )

    called = []

    async def tracking_tool(**kw):
        called.append(kw.get("query", ""))
        return "res"

    deps = _make_deps({"web_search": tracking_tool})
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("test", history, model="test-model", tagged=True, streaming=True, deps=deps):
        tokens.append(t)

    tcs_events = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    calling = [t for t in tcs_events if t["status"] == "calling"]
    ok = [t for t in tcs_events if t["status"] == "ok"]
    assert len(calling) >= 1
    assert len(ok) == 3
    assert len(called) == 3

    mock_chat.assert_not_called()


@pytest.mark.anyio
@patch("src.llm.client.chat", new_callable=AsyncMock)
@patch("src.llm.client.chat_stream")
async def test_streaming_no_tools_from_stream(mock_stream, mock_chat):
    from src.core.orchestrator import chat_stream

    mock_stream.side_effect = _make_stream_mock([
        [("reasoning", "pensando..."), ("content", "respuesta")],
    ])

    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("test", history, model="test-model", tagged=True, streaming=True, deps=_make_deps({})):
        tokens.append(t)

    types = [t[0] for t in tokens]
    assert "content" in types
    assert "tool_call" not in types
    mock_chat.assert_not_called()


@pytest.mark.anyio
@patch("src.llm.client.chat", new_callable=AsyncMock)
@patch("src.llm.client.chat_stream")
async def test_streaming_content_then_tool(mock_stream, mock_chat):
    from src.core.orchestrator import chat_stream

    tcs = [_make_tool_call_obj("web_search", {"query": "test"}, "c1")]
    mock_stream.side_effect = _make_stream_mock(
        [
            [
                ("reasoning", "thinking..."),
                ("content", "Let me search"),
                ("tool_call", json.dumps({"name": "web_search", "args": {}, "status": "calling"})),
            ],
            [("content", "Resultado.")],
        ],
        tool_calls_by_call=[tcs, None],
    )

    async def mock_tool(**kw):
        return "ok"

    deps = _make_deps({"web_search": mock_tool})

    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("test", history, model="test-model", tagged=True, streaming=True, deps=deps):
        tokens.append(t)

    types = [t[0] for t in tokens]
    assert "reasoning" in types, f"Falta reasoning, types={types}"
    assert "content" in types, f"Falta content, types={types}"

    tool_msgs = [m for m in history if (m["role"] if isinstance(m, dict) else m.role) == "tool"]
    assert len(tool_msgs) == 1

    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("Let me search" in c for c in contents) or any("Resultado" in c for c in contents)

    mock_chat.assert_not_called()


@pytest.mark.anyio
@patch("src.llm.client.chat", new_callable=AsyncMock)
@patch("src.llm.client.chat_stream")
async def test_streaming_session_id_propagates(mock_stream, mock_chat):
    from src.api.session import ensure_session
    await ensure_session("ses-s")
    from src.core.orchestrator import chat_stream

    tcs = [_make_tool_call_obj("web_search", {"query": "x"}, "c1")]
    mock_stream.side_effect = _make_stream_mock(
        [
            [("tool_call", json.dumps({"name": "web_search", "args": {}, "status": "calling"}))],
            [("content", "done")],
        ],
        tool_calls_by_call=[tcs, None],
    )

    captured = {}

    async def tracking_tool(**kw):
        captured["session_id"] = kw.get("_session_id")
        return "ok"

    deps = _make_deps({"web_search": tracking_tool})
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("test", history, model="test-model", session_id="ses-s", tagged=True, streaming=True, deps=deps):
        tokens.append(t)

    assert captured.get("session_id") == "ses-s"
    mock_chat.assert_not_called()
