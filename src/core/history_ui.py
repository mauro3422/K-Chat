import json
from typing import Any

from src.core.history_contract import HistoryMessage


def _get_field(msg: Any, key: str, default: Any = None) -> Any:
    if hasattr(msg, key):
        return getattr(msg, key)
    if hasattr(msg, "get"):
        try:
            return msg.get(key, default)
        except TypeError:
            pass
    try:
        return msg[key]
    except Exception:
        return default


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value


def _coerce_message(msg: Any) -> HistoryMessage:
    if isinstance(msg, HistoryMessage):
        return msg
    tool_calls_raw = _get_field(msg, "tool_calls")
    return HistoryMessage(
        role=_get_field(msg, "role", ""),
        content=_get_field(msg, "content"),
        created_at=_get_field(msg, "created_at", ""),
        reasoning=_get_field(msg, "reasoning", "") or "",
        phases=_get_field(msg, "phases", "[]") or "[]",
        tool_calls=_parse_json_field(tool_calls_raw),
        tool_call_id=_get_field(msg, "tool_call_id"),
    )


def filter_messages_for_ui(raw_msgs: list[Any]) -> list[HistoryMessage]:
    """
    Filtra los mensajes para ser presentados en la UI:
    - Excluye los mensajes con rol 'tool'.
    - Conserva solo el último mensaje 'assistant' de cada secuencia o turno.
    """
    msgs: list[HistoryMessage] = []
    current_assistant_group: list[HistoryMessage] = []
    for msg in raw_msgs:
        msg_obj = _coerce_message(msg)
        role = msg_obj.role
        if role == "user":
            if current_assistant_group:
                msgs.append(current_assistant_group[-1])
                current_assistant_group = []
            msgs.append(msg_obj)
        elif role == "assistant":
            current_assistant_group.append(msg_obj)
        elif role == "tool":
            continue
        else:
            if current_assistant_group:
                msgs.append(current_assistant_group[-1])
                current_assistant_group = []
            msgs.append(msg_obj)
    if current_assistant_group:
        msgs.append(current_assistant_group[-1])
    return msgs


def match_tools_to_msgs(msgs: list[Any], all_tools: list[Any]) -> dict[str, list[Any]]:
    """
    Asocia cronológicamente las llamadas a herramientas (tool_calls)
    con los correspondientes mensajes 'assistant' de la UI.
    """
    msg_tools = {}
    sorted_tools = sorted(all_tools, key=lambda t: _get_field(t, "created_at"))
    assistant_indices = [i for i, msg in enumerate(msgs) if _get_field(msg, "role") == "assistant"]
    tool_ptr = 0
    for msg_idx in assistant_indices:
        ts = _get_field(msgs[msg_idx], "created_at")
        matched = []
        while tool_ptr < len(sorted_tools):
            t = sorted_tools[tool_ptr]
            if _get_field(t, "created_at") <= ts:
                matched.append(t)
                tool_ptr += 1
            else:
                break
        msg_tools[ts] = matched
    return msg_tools
