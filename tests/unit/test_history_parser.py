
from src.core.history_parser import _parse_rows, _sanitize_messages


def test_parse_rows_valid():
    rows = [
        ("user", "hola", None, "2025-01-01T10:00:00", None, None, None, None),
        ("assistant", "respuesta", None, "2025-01-01T10:00:01", None, None, None, None),
    ]
    result = _parse_rows(rows)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "[2025-01-01 10:00:00] hola"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "[2025-01-01 10:00:01] respuesta"


def test_parse_rows_incomplete_row():
    rows = [
        ("user", "hola", None, "2025-01-01T10:00:00"),
    ]
    result = _parse_rows(rows)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "[2025-01-01 10:00:00] hola"


def test_sanitize_messages_assistant_with_tool_calls_no_content():
    tool_calls = [{"id": "tc1", "type": "function", "function": {"name": "web_search"}}]
    raw_msgs = [
        {"role": "assistant", "content": None, "tool_calls": tool_calls},
        {"role": "tool", "content": "result", "tool_call_id": "tc1"},
    ]
    result = _sanitize_messages(raw_msgs)
    assert len(result) == 2
    assert result[0]["tool_calls"] == tool_calls


def test_sanitize_messages_assistant_empty():
    raw_msgs = [
        {"role": "assistant", "content": ""},
    ]
    result = _sanitize_messages(raw_msgs)
    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert result[0]["content"] == ""
