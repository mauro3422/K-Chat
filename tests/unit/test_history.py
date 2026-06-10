


from src.core.history import filter_messages_for_ui, match_tools_to_msgs

def test_filter_messages_for_ui_complete_turn():
    """
    Verifica que filter_messages_for_ui:
    - Excluya los mensajes de tipo 'tool'.
    - Deje pasar los mensajes 'user'.
    - Conserve solo el último mensaje 'assistant' de cada secuencia continua.
    """
    raw_msgs = [
        ("user", "Hola", "model-1", "2026-06-09 10:00:00", None, None),
        ("assistant", "Pensando...", "model-1", "2026-06-09 10:00:01", "R1", "[]"),
        ("assistant", "Casi listo...", "model-1", "2026-06-09 10:00:02", "R2", "[]"),
        ("assistant", "Hola! En qué puedo ayudarte?", "model-1", "2026-06-09 10:00:03", "R3", "[]"),
        ("tool", "tool result", "model-1", "2026-06-09 10:00:04", None, None),
        ("user", "Dame más info", "model-1", "2026-06-09 10:00:05", None, None),
    ]

    filtered = filter_messages_for_ui(raw_msgs)

    # Debería quedar:
    # 1. user: "Hola"
    # 2. assistant: "Hola! En qué puedo ayudarte?" (el último del grupo)
    # 3. user: "Dame más info"
    assert len(filtered) == 3
    assert filtered[0][0] == "user"
    assert filtered[0][1] == "Hola"
    
    assert filtered[1][0] == "assistant"
    assert filtered[1][1] == "Hola! En qué puedo ayudarte?"
    
    assert filtered[2][0] == "user"
    assert filtered[2][1] == "Dame más info"


def test_filter_messages_for_ui_incomplete_turn():
    """
    Verifica que si el turno del asistente está incompleto (es decir,
    el último mensaje en la base de datos es del asistente),
    filter_messages_for_ui conserve el último mensaje del asistente.
    """
    raw_msgs = [
        ("user", "Hola", "model-1", "2026-06-09 10:00:00", None, None),
        ("assistant", "Pensando paso 1...", "model-1", "2026-06-09 10:00:01", "R1", "[]"),
        ("assistant", "Pensando paso 2...", "model-1", "2026-06-09 10:00:02", "R2", "[]"),
    ]

    filtered = filter_messages_for_ui(raw_msgs)

    # Debería quedar:
    # 1. user: "Hola"
    # 2. assistant: "Pensando paso 2..."
    assert len(filtered) == 2
    assert filtered[0][0] == "user"
    assert filtered[1][0] == "assistant"
    assert filtered[1][1] == "Pensando paso 2..."


def test_match_tools_to_msgs_chronological():
    """
    Verifica que match_tools_to_msgs asocie correctamente las llamadas
    a herramientas con cada mensaje 'assistant' en base a sus timestamps.
    """
    msgs = [
        ("user", "Hola", "model-1", 10, None, None),
        ("assistant", "Respuesta 1", "model-1", 20, "R1", "[]"),
        ("user", "Búsqueda", "model-1", 30, None, None),
        ("assistant", "Respuesta 2", "model-1", 50, "R2", "[]"),
    ]

    # all_tools tiene formato: (name, inp, status, timestamp, turn)
    all_tools = [
        ("tool_a", "arg_a", "ok", 15, 1),
        ("tool_b", "arg_b", "ok", 40, 1),
        ("tool_c", "arg_c", "error", 45, 1),
        ("tool_d", "arg_d", "ok", 55, 1),  # Esta ocurre después de la Respuesta 2 (ts=50), no debe asociarse
    ]

    matched = match_tools_to_msgs(msgs, all_tools)

    # Para Respuesta 1 (ts=20): debe tener tool_a (ts=15)
    assert 20 in matched
    assert len(matched[20]) == 1
    assert matched[20][0][0] == "tool_a"

    # Para Respuesta 2 (ts=50): debe tener tool_b (ts=40) y tool_c (ts=45)
    assert 50 in matched
    assert len(matched[50]) == 2
    assert matched[50][0][0] == "tool_b"
    assert matched[50][1][0] == "tool_c"
