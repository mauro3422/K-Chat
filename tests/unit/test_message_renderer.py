import json

from web.services.message_renderer_contract import MessageRenderDeps
from web.services.message_renderer import render_session_messages


def make_deps(**overrides):
    base = MessageRenderDeps(
        get_session_messages_fn=lambda session_id: [],
        filter_messages_fn=lambda msgs: msgs,
        get_tool_history_fn=lambda session_id, limit: [],
        match_tools_fn=lambda msgs, tools: {},
        get_widget_states_fn=lambda session_id: {},
        extract_inline_widget_states_fn=lambda msgs: {},
        render_msg_fn=None,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_render_session_messages_empty():
    """Empty message list should return empty list and empty widget states."""
    data = render_session_messages("test-sid", deps=make_deps())
    assert data["messages"] == []
    assert data["widget_states"] == {}


def test_render_session_messages_plain_user():
    """A plain user message should be returned with correct fields."""
    msgs = [{"role": "user", "content": "Hello world", "created_at": 1000.0, "reasoning": "", "phases": "[]"}]
    data = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert len(data["messages"]) == 1
    msg = data["messages"][0]
    assert msg["role"] == "user"
    assert msg["content"] == "Hello world"
    assert msg["ts"] == 1000.0


def test_render_session_messages_assistant_legacy():
    """Legacy assistant message (no phases) returns tool calls and reasoning."""
    msgs = [{"role": "assistant", "content": "Response text", "created_at": 2000.0, "reasoning": "Deep thought", "phases": "[]"}]
    tool_rows = [{"tool_name": "web_search", "input": "query", "status": "ok", "created_at": 1500, "turn": 1}]
    data = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
            get_tool_history_fn=lambda session_id, limit: tool_rows,
            match_tools_fn=lambda rows, tools: {2000.0: tool_rows},
        ),
    )

    assert len(data["messages"]) == 1
    msg = data["messages"][0]
    assert msg["role"] == "assistant"
    assert msg["content"] == "Response text"
    assert msg["reasoning"] == "Deep thought"
    assert len(msg["matched_tools"]) == 1
    assert msg["matched_tools"][0]["tool_name"] == "web_search"
    assert msg["matched_tools"][0]["status"] == "ok"


def test_render_session_messages_xss_escaping():
    """HTML escaping is handled on client-side, backend returns raw data."""
    raw_content = '<script>alert("xss")</script>'
    msgs = [{"role": "user", "content": raw_content, "created_at": 3000.0, "reasoning": "", "phases": "[]"}]
    data = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert data["messages"][0]["content"] == raw_content


def test_render_session_messages_multiple():
    """Multiple messages of alternating roles returned in order."""
    msgs = [
        {"role": "user", "content": "First", "created_at": 1.0, "reasoning": "", "phases": "[]"},
        {"role": "assistant", "content": "Second", "created_at": 2.0, "reasoning": "", "phases": "[]"},
        {"role": "user", "content": "Third", "created_at": 3.0, "reasoning": "", "phases": "[]"},
    ]
    data = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert len(data["messages"]) == 3
    assert data["messages"][0]["content"] == "First"
    assert data["messages"][1]["content"] == "Second"
    assert data["messages"][2]["content"] == "Third"


def test_render_session_messages_widget_states_metadata():
    """Widget states are returned directly in the dictionary."""
    data = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_widget_states_fn=lambda session_id: {"w1": {"x": 1}},
        ),
    )

    assert data["widget_states"] == {"w1": {"x": 1}}


def test_render_session_messages_with_phases():
    """Messages with phases data are structured correctly."""
    phases = [{"reasoning": "Step 1", "content": "Part A"}]
    msgs = [{"role": "assistant", "content": "Part A", "created_at": 4000.0, "reasoning": "", "phases": json.dumps(phases)}]
    data = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert len(data["messages"]) == 1
    msg = data["messages"][0]
    assert msg["phases"] == phases
    assert msg["content"] == "Part A"
