import json
import html
import inspect

from src.core.history_ui import filter_messages_for_ui, match_tools_to_msgs
from src.api.messages import get_session_messages
from src.api.tools import get_tool_history
from src.api.widgets import get_widget_states
from web.services.widget_contract import extract_inline_widget_states
from web.services.message_renderer_contract import MessageRenderDeps


def _resolve_render_deps(deps: MessageRenderDeps | None = None) -> MessageRenderDeps:
    return deps or MessageRenderDeps()


async def _call_with_repos(fn, session_id: str, repos, *args):
    params = inspect.signature(fn).parameters
    if 'repos' in params:
        result = fn(session_id, *args, repos=repos)
    else:
        result = fn(session_id, *args)
    if inspect.isawaitable(result):
        return await result
    return result


async def render_session_messages(session_id: str, deps: MessageRenderDeps | None = None) -> dict:
    """Returns a dict containing messages and widget states for a session."""
    _deps = _resolve_render_deps(deps)
    get_session_messages_fn = _deps.get_session_messages_fn or get_session_messages
    filter_messages_fn = _deps.filter_messages_fn or filter_messages_for_ui
    get_tool_history_fn = _deps.get_tool_history_fn or get_tool_history
    match_tools_fn = _deps.match_tools_fn or match_tools_to_msgs
    get_widget_states_fn = _deps.get_widget_states_fn or get_widget_states
    extract_inline_widget_states_fn = _deps.extract_inline_widget_states_fn or extract_inline_widget_states
    repos = _deps.repos

    raw_msgs = await _call_with_repos(get_session_messages_fn, session_id, repos)
    msgs = filter_messages_fn(raw_msgs)

    all_tools = await _call_with_repos(get_tool_history_fn, session_id, repos, 100)
    msg_tool_map = match_tools_fn(msgs, all_tools)
    widget_states_raw = get_widget_states_fn(session_id)
    widget_states = await widget_states_raw if inspect.isawaitable(widget_states_raw) else widget_states_raw
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

