import os, sys, json, tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MEMORY_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_core.db")

from src.memory import init_db
init_db()


def make_choice(content=None, finish_reason="stop", tool_calls=None, reasoning_content=None):
    """Build a mock ChatCompletion Choice."""
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


@patch("src.core.llm_chat")
def test_no_tools(mock_chat):
    """Simple text response, no tools needed."""
    mock_chat.return_value = make_choice(content="¡Hola!")
    from src.core import chat_stream

    history = [{"role": "system", "content": "test"}]
    tokens = list(chat_stream("Hola!", history, model="test-model", tagged=True))
    contents = [t for t in tokens if t[0] == "content"]
    full = "".join(t[1] for t in contents)
    assert "¡Hola!" in full
    # Final message appended to history
    assert history[-1]["role"] == "user"
    mock_chat.assert_called_once()


@patch("src.core.llm_chat")
def test_tool_call_then_response(mock_chat):
    """Model calls a tool, then responds."""
    from src.core import chat_stream

    # First call: tool_calls
    mock_chat.side_effect = [
        make_choice(
            content="Let me search...",
            finish_reason="tool_calls",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "test"}}],
            reasoning_content="I need info",
        ),
        # Second call after tool result: final answer
        make_choice(content="Aquí está la info.", reasoning_content="Done thinking"),
    ]

    history = [{"role": "system", "content": "test"}]
    debug = {}
    with patch("src.core.TOOL_MAP", {"web_search": lambda **kw: "ok result"}):
        tokens = list(chat_stream("Busca algo", history, model="test-model", tagged=True, debug=debug))

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
    assert debug["model"] == "test-model"
    assert len(debug["tool_calls"]) >= 1
    assert "Done thinking" in debug.get("reasoning", "")


@patch("src.core.llm_chat")
def test_tool_error(mock_chat):
    """Tool raises an exception."""
    from src.core import chat_stream

    # Use a real side effect that raises
    def failing_run(**kwargs):
        raise ValueError("API error")

    mock_chat.side_effect = [
        make_choice(
            finish_reason="tool_calls",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "test"}}],
        ),
        make_choice(content="Lo siento, hubo un error."),
    ]

    history = [{"role": "system", "content": "test"}]
    # We need to mock the TOOL_MAP to raise
    with patch("src.core.TOOL_MAP", {"web_search": failing_run}):
        tokens = list(chat_stream("test", history, model="test-model", tagged=True))

    tcs = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    assert any(t["status"] == "error" for t in tcs)


@patch("src.core.llm_chat")
def test_session_id_propagates_to_tools(mock_chat):
    """session_id is passed as _session_id to tools."""
    from src.core import chat_stream

    captured = {}
    def tracking_tool(**kwargs):
        captured["session_id"] = kwargs.get("_session_id")
        return "ok"

    mock_chat.side_effect = [
        make_choice(
            finish_reason="tool_calls",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "x"}}],
        ),
        make_choice(content="done"),
    ]

    history = [{"role": "system", "content": "test"}]
    with patch("src.core.TOOL_MAP", {"web_search": tracking_tool}):
        list(chat_stream("test", history, model="test-model", session_id="ses-123", tagged=True))

    assert captured.get("session_id") == "ses-123"


@patch("src.core.llm_chat")
def test_multiple_tool_calls_same_turn(mock_chat):
    """Multiple tools called in a single turn."""
    from src.core import chat_stream

    tools_called = []

    def tracking_tool(**kwargs):
        tools_called.append(kwargs.get("_session_id"))
        return "result"

    mock_chat.side_effect = [
        make_choice(
            finish_reason="tool_calls",
            tool_calls=[
                {"id": "c1", "name": "web_search", "args": {"query": "test1"}},
                {"id": "c2", "name": "web_search", "args": {"query": "test2"}},
                {"id": "c3", "name": "web_search", "args": {"query": "test3"}},
            ],
        ),
        make_choice(content="Resultados combinados."),
    ]

    history = [{"role": "system", "content": "test"}]
    with patch("src.core.TOOL_MAP", {"web_search": tracking_tool}):
        tokens = list(chat_stream("test", history, model="test-model", session_id="ses-1", tagged=True))

    tcs = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    calling = [t for t in tcs if t["status"] == "calling"]
    ok = [t for t in tcs if t["status"] == "ok"]
    assert len(calling) == 3
    assert len(ok) == 3
    assert len(tools_called) == 3


@patch("src.core.llm_chat")
def test_mixed_tool_results(mock_chat):
    """One tool succeeds, one fails in the same turn."""
    from src.core import chat_stream

    call_count = [0]

    def flip_flop(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("fail")
        return "ok result"

    mock_chat.side_effect = [
        make_choice(
            finish_reason="tool_calls",
            tool_calls=[
                {"id": "c1", "name": "web_search", "args": {"query": "a"}},
                {"id": "c2", "name": "web_search", "args": {"query": "b"}},
            ],
        ),
        make_choice(content="done"),
    ]

    history = [{"role": "system", "content": "test"}]
    with patch("src.core.TOOL_MAP", {"web_search": flip_flop}):
        tokens = list(chat_stream("test", history, model="test-model", session_id="ses-2", tagged=True))

    tcs = [json.loads(t[1]) for t in tokens if t[0] == "tool_call"]
    errors = [t for t in tcs if t["status"] == "error"]
    oks = [t for t in tcs if t["status"] == "ok"]
    assert len(errors) == 1
    assert len(oks) >= 1


@patch("src.core.llm_chat")
def test_tool_result_truncation(mock_chat):
    """Tool result >2000 chars gets truncated."""
    from src.core import chat_stream

    long_result = "x" * 3000

    mock_chat.side_effect = [
        make_choice(
            finish_reason="tool_calls",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "test"}}],
        ),
        make_choice(content="done"),
    ]

    history = [{"role": "system", "content": "test"}]
    with patch("src.core.TOOL_MAP", {"web_search": lambda **kw: long_result}):
        tokens = list(chat_stream("test", history, model="test-model", session_id="ses-3", tagged=True))

    # Check history has truncated tool result
    tool_msgs = [m for m in history if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert len(tool_msgs[0]["content"]) == 2014  # 2000 + "\n...[truncado]"


@patch("src.core.llm_chat")
def test_empty_message(mock_chat):
    """Empty message still works."""
    from src.core import chat_stream

    mock_chat.return_value = make_choice(content="OK")
    history = [{"role": "system", "content": "test"}]
    tokens = list(chat_stream("", history, model="test-model", tagged=True))
    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("OK" in c for c in contents)


@patch("src.core.llm_chat")
def test_chat_non_streaming(mock_chat):
    """chat() returns response and updated history."""
    mock_chat.return_value = make_choice(content="Respuesta de prueba")
    from src.core import chat

    resp, history = chat("Hola", None)
    assert resp == "Respuesta de prueba"
    assert len(history) >= 2
    assert history[-1]["role"] == "assistant"
    assert history[-1]["content"] == "Respuesta de prueba"
