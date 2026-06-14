import json

from src.core.history_ui import filter_messages_for_ui, match_tools_to_msgs
from src.memory.repos import get_repos
from web.services.widget_contract import extract_inline_widget_states
from web.services.message_renderer_contract import MessageRenderDeps


def _resolve_render_deps(deps: MessageRenderDeps | None = None) -> MessageRenderDeps:
    return deps or MessageRenderDeps()


async def render_session_messages(session_id: str, deps: MessageRenderDeps | None = None) -> dict:
    """Returns a dict containing messages and widget states for a session."""
    _deps = _resolve_render_deps(deps)
    filter_messages_fn = _deps.filter_messages_fn or filter_messages_for_ui
    match_tools_fn = _deps.match_tools_fn or match_tools_to_msgs
    extract_inline_widget_states_fn = _deps.extract_inline_widget_states_fn or extract_inline_widget_states
    repos = _deps.repos or get_repos()

    raw_msgs = await repos.messages.get_session_messages(session_id)
    msgs = filter_messages_fn(raw_msgs)

    all_tools = await repos.tool_calls.get_history(session_id, 100)
    msg_tool_map = match_tools_fn(msgs, all_tools)
    widget_states = await repos.widget_states.get_states(session_id)
    widget_states.update(extract_inline_widget_states_fn(msgs))

    from web.ui_utils import _ensure_dict
    formatted_msgs = []
    for row in msgs:
        role = row.role
        content = row.content
        ts = row.created_at
        reasoning = row.reasoning
        phases_str = row.phases
        matched = msg_tool_map.get(ts, []) if role == "assistant" else []

        matched_dicts = [_ensure_dict(t) for t in matched]

        phases = None
        if phases_str and phases_str != "[]":
            try:
                phases = json.loads(phases_str)
            except (json.JSONDecodeError, TypeError):
                pass

        formatted_msgs.append({
            "role": role,
            "content": content,
            "reasoning": reasoning,
            "ts": ts,
            "phases": phases,
            "matched_tools": matched_dicts
        })

    return {
        "messages": formatted_msgs,
        "widget_states": widget_states
    }
