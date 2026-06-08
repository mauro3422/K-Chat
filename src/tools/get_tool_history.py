from src.memory import get_tool_history as _get_tool_history

DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_tool_history",
        "description": "Obtiene el historial de herramientas usadas en la sesion actual. Util para recordar que tools se usaron y como.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Cuantas tools recordar (max 20, default 5)"
                }
            },
            "required": []
        }
    }
}

def run(limit: int = 5, _session_id: str = None) -> str:
    if not _session_id:
        return "No hay sesion activa."
    try:
        rows = _get_tool_history(_session_id, limit=min(limit, 20))
    except Exception as e:
        return f"[ERROR]: No se pudo obtener el historial de herramientas: {e}"
    if not rows:
        return "No se usaron herramientas en esta sesion aun."
    lines = []
    for name, inp, status, ts, *_ in rows:
        lines.append(f"[{name}] ({status}) input: {inp} - {ts}")
    return "\n".join(lines)
