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


def run(**kwargs) -> str:
    limit = int(kwargs.get("limit", kwargs.get("max_results", kwargs.get("count", kwargs.get("n", 5)))))
    _session_id = kwargs.get("_session_id")
    _repos = kwargs.get("_repos")
    if not _session_id:
        return "No active session."
    if _repos is None:
        return "[ERROR] Missing repositories."
    try:
        rows = _repos.tool_calls.get_history(_session_id, limit=min(limit, 20))
    except Exception:
        return "[ERROR] Could not retrieve the tool history."
    if not rows:
        return "No tools have been used in this session yet."
    lines = []
    for row in rows:
        lines.append(f"[{row['tool_name']}] ({row['status']}) input: {row['input']} - {row['created_at']}")
    return "\n".join(lines)
