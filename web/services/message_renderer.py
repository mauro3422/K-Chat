import json
import html

from src.core.history_ui import filter_messages_for_ui, match_tools_to_msgs
from src.api.messages import get_session_messages
from src.api.tools import get_tool_history
from src.api.widgets import get_widget_states
from web.ui_utils import render_msg_with_phases
from web.services.widget_contract import extract_inline_widget_states
from web.services.message_renderer_contract import MessageRenderDeps


def _resolve_render_deps(deps: MessageRenderDeps | None = None) -> MessageRenderDeps:
    return deps or MessageRenderDeps()


def render_session_messages(session_id: str, deps: MessageRenderDeps | None = None) -> str:
    """Renders the HTML message list for a session, including widgets and phases."""
    _deps = _resolve_render_deps(deps)
    get_session_messages_fn = _deps.get_session_messages_fn or get_session_messages
    filter_messages_fn = _deps.filter_messages_fn or filter_messages_for_ui
    get_tool_history_fn = _deps.get_tool_history_fn or get_tool_history
    match_tools_fn = _deps.match_tools_fn or match_tools_to_msgs
    get_widget_states_fn = _deps.get_widget_states_fn or get_widget_states
    extract_inline_widget_states_fn = _deps.extract_inline_widget_states_fn or extract_inline_widget_states
    render_msg_fn = _deps.render_msg_fn or render_msg_with_phases

    raw_msgs = get_session_messages_fn(session_id)
    msgs = filter_messages_fn(raw_msgs)

    all_tools = get_tool_history_fn(session_id, 100)
    msg_tool_map = match_tools_fn(msgs, all_tools)
    widget_states = get_widget_states_fn(session_id)
    widget_states.update(extract_inline_widget_states_fn(msgs))

    widget_states_json = json.dumps(widget_states, ensure_ascii=False)

    parts = [
        f'<div id="messages-metadata" data-widget-states="{html.escape(widget_states_json)}" style="display:none;"></div>',
        '<div class="main-header">',
        '<span class="debug-toggle">&#128202; Debug</span>',
        '</div>',
        '<div id="messages">'
    ]

    for row in msgs:
        role = row.role if hasattr(row, "role") else row["role"]
        content = row.content if hasattr(row, "content") else row["content"]
        ts = row.created_at if hasattr(row, "created_at") else row["created_at"]
        reasoning = row.reasoning if hasattr(row, "reasoning") else row["reasoning"]
        phases_str = row.phases if hasattr(row, "phases") else row["phases"]
        matched = msg_tool_map.get(ts, []) if role == "assistant" else []
        phases = None
        if phases_str and phases_str != "[]":
            try:
                phases = json.loads(phases_str)
            except (json.JSONDecodeError, TypeError):
                pass

        parts.append(render_msg_fn(role, content, reasoning, matched, ts, phases))

    if not msgs:
        parts.append('<div class="empty-state">Send a message to start</div>')
    parts.append('</div>')

    parts.append(
        '<form id="chat-form">'
        '<div class="input-row">'
        '<textarea id="msg-input" placeholder="Escribe un mensaje..." autofocus rows="1"></textarea>'
        '<button type="button" id="asr-mic-btn" class="asr-mic-idle" title="Grabar voz (Speech-to-Text)">🎤</button>'
        '<button type="submit">Send</button>'
        '</div>'
        '<span id="spinner" class="htmx-indicator"></span>'
        '</form>'
    )

    return "\n".join(parts)
