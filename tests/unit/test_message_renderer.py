import json
import html
from unittest.mock import patch

from web.services.message_renderer import render_session_messages


def test_render_session_messages_empty():
    """Empty message list should render empty-state div."""
    with (
        patch("web.services.message_renderer.get_session_messages", return_value=[]),
        patch("web.services.message_renderer.filter_messages_for_ui", return_value=[]),
        patch("web.services.message_renderer.get_tool_history", return_value=[]),
        patch("web.services.message_renderer.match_tools_to_msgs", return_value={}),
        patch("web.services.message_renderer.get_widget_states", return_value={}),
    ):
        html_out = render_session_messages("test-sid")
    assert 'Send a message to start' in html_out
    assert '<div id="messages">' in html_out
    assert '<form id="chat-form">' in html_out


def test_render_session_messages_plain_user():
    """A plain user message should be rendered with correct CSS classes and label."""
    msgs = [{"role": "user", "content": "Hello world", "created_at": 1000.0, "reasoning": "", "phases": "[]"}]
    with (
        patch("web.services.message_renderer.get_session_messages", return_value=msgs),
        patch("web.services.message_renderer.filter_messages_for_ui", return_value=msgs),
        patch("web.services.message_renderer.get_tool_history", return_value=[]),
        patch("web.services.message_renderer.match_tools_to_msgs", return_value={}),
        patch("web.services.message_renderer.get_widget_states", return_value={}),
    ):
        html_out = render_session_messages("test-sid")

    assert '<div class="msg user">' in html_out
    assert '<div class="msg-label">Tu</div>' in html_out
    assert 'Hello world' in html_out
    assert '1000.0' in html_out or '1000.' in html_out


def test_render_session_messages_assistant_legacy():
    """Legacy assistant message (no phases) renders tool calls and reasoning."""
    msgs = [{"role": "assistant", "content": "Response text", "created_at": 2000.0, "reasoning": "Deep thought", "phases": "[]"}]
    with (
        patch("web.services.message_renderer.get_session_messages", return_value=msgs),
        patch("web.services.message_renderer.filter_messages_for_ui", return_value=msgs),
        patch("web.services.message_renderer.get_tool_history", return_value=[{"tool_name": "web_search", "input": "query", "status": "ok", "created_at": 1500, "turn": 1}]),
        patch("web.services.message_renderer.match_tools_to_msgs", return_value={2000.0: [{"tool_name": "web_search", "input": "query", "status": "ok", "created_at": 1500, "turn": 1}]}),
        patch("web.services.message_renderer.get_widget_states", return_value={}),
    ):
        html_out = render_session_messages("test-sid")

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
    with (
        patch("web.services.message_renderer.get_session_messages", return_value=msgs),
        patch("web.services.message_renderer.filter_messages_for_ui", return_value=msgs),
        patch("web.services.message_renderer.get_tool_history", return_value=[]),
        patch("web.services.message_renderer.match_tools_to_msgs", return_value={}),
        patch("web.services.message_renderer.get_widget_states", return_value={}),
    ):
        html_out = render_session_messages("test-sid")

    assert '<script>' not in html_out
    assert '&lt;script&gt;' in html_out


def test_render_session_messages_multiple():
    """Multiple messages of alternating roles render in order."""
    msgs = [
        {"role": "user", "content": "First", "created_at": 1.0, "reasoning": "", "phases": "[]"},
        {"role": "assistant", "content": "Second", "created_at": 2.0, "reasoning": "", "phases": "[]"},
        {"role": "user", "content": "Third", "created_at": 3.0, "reasoning": "", "phases": "[]"},
    ]
    with (
        patch("web.services.message_renderer.get_session_messages", return_value=msgs),
        patch("web.services.message_renderer.filter_messages_for_ui", return_value=msgs),
        patch("web.services.message_renderer.get_tool_history", return_value=[]),
        patch("web.services.message_renderer.match_tools_to_msgs", return_value={}),
        patch("web.services.message_renderer.get_widget_states", return_value={}),
    ):
        html_out = render_session_messages("test-sid")

    assert html_out.index("First") < html_out.index("Second") < html_out.index("Third")


def test_render_session_messages_widget_states_metadata():
    """Widget states are serialised into a data attribute."""
    with (
        patch("web.services.message_renderer.get_session_messages", return_value=[]),
        patch("web.services.message_renderer.filter_messages_for_ui", return_value=[]),
        patch("web.services.message_renderer.get_tool_history", return_value=[]),
        patch("web.services.message_renderer.match_tools_to_msgs", return_value={}),
        patch("web.services.message_renderer.get_widget_states", return_value={"w1": {"x": 1}}),
    ):
        html_out = render_session_messages("test-sid")

    expected_meta = html.escape(json.dumps({"w1": {"x": 1}}, ensure_ascii=False))
    assert expected_meta in html_out
    assert 'id="messages-metadata"' in html_out


def test_render_session_messages_with_phases():
    """Messages with phases data render phase-structured HTML."""
    phases = json.dumps([{"reasoning": "Step 1", "content": "Part A"}])
    msgs = [{"role": "assistant", "content": "Part A", "created_at": 4000.0, "reasoning": "", "phases": phases}]
    with (
        patch("web.services.message_renderer.get_session_messages", return_value=msgs),
        patch("web.services.message_renderer.filter_messages_for_ui", return_value=msgs),
        patch("web.services.message_renderer.get_tool_history", return_value=[]),
        patch("web.services.message_renderer.match_tools_to_msgs", return_value={}),
        patch("web.services.message_renderer.get_widget_states", return_value={}),
    ):
        html_out = render_session_messages("test-sid")

    assert "Step 1" in html_out
    assert "Part A" in html_out
