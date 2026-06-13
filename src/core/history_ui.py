from typing import Any


def filter_messages_for_ui(raw_msgs: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """
    Filtra los mensajes para ser presentados en la UI:
    - Excluye los mensajes con rol 'tool'.
    - Conserva solo el último mensaje 'assistant' de cada secuencia o turno.
    """
    msgs = []
    current_assistant_group = []
    for msg in raw_msgs:
        role = msg["role"]
        if role == "user":
            if current_assistant_group:
                msgs.append(current_assistant_group[-1])
                current_assistant_group = []
            msgs.append(msg)
        elif role == "assistant":
            current_assistant_group.append(msg)
        elif role == "tool":
            continue
        else:
            if current_assistant_group:
                msgs.append(current_assistant_group[-1])
                current_assistant_group = []
            msgs.append(msg)
    if current_assistant_group:
        msgs.append(current_assistant_group[-1])
    return msgs


def match_tools_to_msgs(msgs: list[tuple[Any, ...]], all_tools: list[tuple[Any, ...]]) -> dict[str, list[Any]]:
    """
    Asocia cronológicamente las llamadas a herramientas (tool_calls)
    con los correspondientes mensajes 'assistant' de la UI.
    """
    msg_tools = {}
    sorted_tools = sorted(all_tools, key=lambda t: t["created_at"])
    assistant_indices = [i for i, msg in enumerate(msgs) if msg["role"] == "assistant"]
    tool_ptr = 0
    for msg_idx in assistant_indices:
        ts = msgs[msg_idx]["created_at"]
        matched = []
        while tool_ptr < len(sorted_tools):
            t = sorted_tools[tool_ptr]
            if t["created_at"] <= ts:
                matched.append(t)
                tool_ptr += 1
            else:
                break
        msg_tools[ts] = matched
    return msg_tools
