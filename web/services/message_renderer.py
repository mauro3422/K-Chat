import json
import html

from src.api.history import filter_messages_for_ui, match_tools_to_msgs
from src.api.messages import get_session_messages
from src.api.tools import get_tool_history
from src.api.widgets import get_widget_states
from web.ui_utils import render_msg_with_phases
from web.services.widget_contract import extract_inline_widget_states


def render_session_messages(session_id: str) -> str:
    """Renders the HTML message list for a session, including widgets and phases."""
    raw_msgs = get_session_messages(session_id)
    msgs = filter_messages_for_ui(raw_msgs)

    all_tools = get_tool_history(session_id, 100)
    msg_tool_map = match_tools_to_msgs(msgs, all_tools)
    widget_states = get_widget_states(session_id)
    widget_states.update(extract_inline_widget_states(msgs))

    widget_states_json = json.dumps(widget_states, ensure_ascii=False)

    parts = [
        f'<div id="messages-metadata" data-widget-states="{html.escape(widget_states_json)}" style="display:none;"></div>',
        '<div class="main-header">',
        '<span class="debug-toggle">&#128202; Debug</span>',
        '</div>',
        '<div id="messages">'
    ]

    for row in msgs:
        role, content, model, ts, reasoning, phases_str = row[:6]
        matched = msg_tool_map.get(ts, []) if role == "assistant" else []
        phases = None
        if phases_str and phases_str != "[]":
            try:
                phases = json.loads(phases_str)
            except (json.JSONDecodeError, TypeError):
                pass

        parts.append(render_msg_with_phases(role, content, reasoning, matched, ts, phases))

    if not msgs:
        parts.append('<div class="empty-state">Send a message to start</div>')
    parts.append('</div>')

    parts.append(
        '<form id="chat-form">'
        '<input type="text" id="msg-input" placeholder="Escribe un mensaje..." autofocus>'
        '<button type="submit">Send</button>'
        '<span id="spinner" class="htmx-indicator"></span>'
        '</form>'
    )

    return "\n".join(parts)
