DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_tool_history",
        "description": "Gets the history of tools used in the current session. Useful to remember which tools were used and how.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "How many tools to recall (max 20, default 5)."
                }
            },
            "required": []
        }
    }
}

_tool_call_repo = None


def _get_tool_call_repo():
    global _tool_call_repo
    if _tool_call_repo is None:
        from src.memory.repositories import ToolCallRepository
        _tool_call_repo = ToolCallRepository()
    return _tool_call_repo


def run(limit: int = 5, _session_id: str | None = None) -> str:
    if not _session_id:
        return "No active session."
    try:
        rows = _get_tool_call_repo().get_history(_session_id, limit=min(limit, 20))
    except Exception:
        return "[ERROR] Could not retrieve the tool history."
    if not rows:
        return "No tools have been used in this session yet."
    lines = []
    for name, inp, status, ts, *_ in rows:
        lines.append(f"[{name}] ({status}) input: {inp} - {ts}")
    return "\n".join(lines)
