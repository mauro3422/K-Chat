import pytest
from src.core.history_ui import filter_messages_for_ui, match_tools_to_msgs

@pytest.mark.anyio
async def test_filter_messages_for_ui_complete_turn():
    """
    Verifica que filter_messages_for_ui:
    - Excluya los mensajes de tipo 'tool'.
    - Deje pasar los mensajes 'user'.
    - Conserve solo el último mensaje 'assistant' de cada secuencia continua.
    """
    raw_msgs = [
        {"role": "user", "content": "Hola", "created_at": "2026-06-09 10:00:00"},
        {"role": "assistant", "content": "Pensando...", "created_at": "2026-06-09 10:00:01"},
        {"role": "assistant", "content": "Casi listo...", "created_at": "2026-06-09 10:00:02"},
        {"role": "assistant", "content": "Hola! En qué puedo ayudarte?", "created_at": "2026-06-09 10:00:03"},
        {"role": "tool", "content": "tool result", "created_at": "2026-06-09 10:00:04"},
        {"role": "user", "content": "Dame más info", "created_at": "2026-06-09 10:00:05"},
    ]

    filtered = filter_messages_for_ui(raw_msgs)

    # Debería quedar:
    # 1. user: "Hola"
    # 2. assistant: "Hola! En qué puedo ayudarte?" (el último del grupo)
    # 3. user: "Dame más info"
    assert len(filtered) == 3
    assert filtered[0].role == "user"
    assert filtered[0].content == "Hola"
    
    assert filtered[1].role == "assistant"
    assert filtered[1].content == "Hola! En qué puedo ayudarte?"
    
    assert filtered[2].role == "user"
    assert filtered[2].content == "Dame más info"


@pytest.mark.anyio
async def test_filter_messages_for_ui_incomplete_turn():
    """
    Verifica que si el turno del asistente está incompleto (es decir,
    el último mensaje en la base de datos es del asistente),
    filter_messages_for_ui conserve el último mensaje del asistente.
    """
    raw_msgs = [
        {"role": "user", "content": "Hola", "created_at": "2026-06-09 10:00:00"},
        {"role": "assistant", "content": "Pensando paso 1...", "created_at": "2026-06-09 10:00:01"},
        {"role": "assistant", "content": "Pensando paso 2...", "created_at": "2026-06-09 10:00:02"},
    ]

    filtered = filter_messages_for_ui(raw_msgs)

    # Debería quedar:
    # 1. user: "Hola"
    # 2. assistant: "Pensando paso 2..."
    assert len(filtered) == 2
    assert filtered[0].role == "user"
    assert filtered[1].role == "assistant"
    assert filtered[1].content == "Pensando paso 2..."


@pytest.mark.anyio
async def test_match_tools_to_msgs_chronological():
    """
    Verifica que match_tools_to_msgs asocie correctamente las llamadas
    a herramientas con cada mensaje 'assistant' en base a sus timestamps.
    """
    msgs = [
        {"role": "user", "content": "Hola", "created_at": 10},
        {"role": "assistant", "content": "Respuesta 1", "created_at": 20},
        {"role": "user", "content": "Búsqueda", "created_at": 30},
        {"role": "assistant", "content": "Respuesta 2", "created_at": 50},
    ]

    all_tools = [
        {"tool_name": "tool_a", "input": "arg_a", "status": "ok", "created_at": 15, "turn": 1},
        {"tool_name": "tool_b", "input": "arg_b", "status": "ok", "created_at": 40, "turn": 1},
        {"tool_name": "tool_c", "input": "arg_c", "status": "error", "created_at": 45, "turn": 1},
        {"tool_name": "tool_d", "input": "arg_d", "status": "ok", "created_at": 55, "turn": 1},
    ]

    matched = match_tools_to_msgs(msgs, all_tools)

    # Para Respuesta 1 (ts=20): debe tener tool_a (ts=15)
    assert 20 in matched
    assert len(matched[20]) == 1
    assert matched[20][0]["tool_name"] == "tool_a"

    # Para Respuesta 2 (ts=50): debe tener tool_b (ts=40) y tool_c (ts=45)
    assert 50 in matched
    assert len(matched[50]) == 2
    assert matched[50][0]["tool_name"] == "tool_b"
    assert matched[50][1]["tool_name"] == "tool_c"
