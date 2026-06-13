import json
import html

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
    """Empty message list should render empty-state div."""
    html_out = render_session_messages("test-sid", deps=make_deps())
    assert 'Send a message to start' in html_out
    assert '<div id="messages">' in html_out
    assert '<form id="chat-form">' in html_out


def test_render_session_messages_plain_user():
    """A plain user message should be rendered with correct CSS classes and label."""
    msgs = [{"role": "user", "content": "Hello world", "created_at": 1000.0, "reasoning": "", "phases": "[]"}]
    html_out = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert '<div class="msg user">' in html_out
    assert '<div class="msg-label">Tu</div>' in html_out
    assert 'Hello world' in html_out
    assert '1000.0' in html_out or '1000.' in html_out


def test_render_session_messages_assistant_legacy():
    """Legacy assistant message (no phases) renders tool calls and reasoning."""
    msgs = [{"role": "assistant", "content": "Response text", "created_at": 2000.0, "reasoning": "Deep thought", "phases": "[]"}]
    tool_rows = [{"tool_name": "web_search", "input": "query", "status": "ok", "created_at": 1500, "turn": 1}]
    html_out = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
            get_tool_history_fn=lambda session_id, limit: tool_rows,
            match_tools_fn=lambda rows, tools: {2000.0: tool_rows},
        ),
    )

    assert '<div class="msg assistant">' in html_out
    assert '<div class="msg-label">Kairos</div>' in html_out
    assert '<summary>Razonamiento</summary>' in html_out
    assert '<div class="rt">Deep thought</div>' in html_out
    assert '<div class="msg-body md-content">Response text</div>' in html_out
    assert 'tc-item ok' in html_out
    assert 'web_search' in html_out


def test_render_session_messages_xss_escaping():
    """User content with HTML/script tags should be HTML-escaped in output."""
    msgs = [{"role": "user", "content": '<script>alert("xss")</script>', "created_at": 3000.0, "reasoning": "", "phases": "[]"}]
    html_out = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert '<script>' not in html_out
    assert '&lt;script&gt;' in html_out


def test_render_session_messages_multiple():
    """Multiple messages of alternating roles render in order."""
    msgs = [
        {"role": "user", "content": "First", "created_at": 1.0, "reasoning": "", "phases": "[]"},
        {"role": "assistant", "content": "Second", "created_at": 2.0, "reasoning": "", "phases": "[]"},
        {"role": "user", "content": "Third", "created_at": 3.0, "reasoning": "", "phases": "[]"},
    ]
    html_out = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert html_out.index("First") < html_out.index("Second") < html_out.index("Third")


def test_render_session_messages_widget_states_metadata():
    """Widget states are serialised into a data attribute."""
    html_out = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_widget_states_fn=lambda session_id: {"w1": {"x": 1}},
        ),
    )

    expected_meta = html.escape(json.dumps({"w1": {"x": 1}}, ensure_ascii=False))
    assert expected_meta in html_out
    assert 'id="messages-metadata"' in html_out


def test_render_session_messages_with_phases():
    """Messages with phases data render phase-structured HTML."""
    phases = json.dumps([{"reasoning": "Step 1", "content": "Part A"}])
    msgs = [{"role": "assistant", "content": "Part A", "created_at": 4000.0, "reasoning": "", "phases": phases}]
    html_out = render_session_messages(
        "test-sid",
        deps=make_deps(
            get_session_messages_fn=lambda session_id: msgs,
            filter_messages_fn=lambda rows: rows,
        ),
    )

    assert "Step 1" in html_out
    assert "Part A" in html_out
