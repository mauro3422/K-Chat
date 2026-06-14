import pytest
from src.core.history_parser import _parse_rows, _sanitize_messages
from src.core.history_contract import HistoryMessage


@pytest.mark.anyio
async def test_parse_rows_valid():
    rows = [
        {"role": "user", "content": "hola", "model": None, "created_at": "2025-01-01T10:00:00", "reasoning": None, "phases": None, "tool_calls": None, "tool_call_id": None},
        {"role": "assistant", "content": "respuesta", "model": None, "created_at": "2025-01-01T10:00:01", "reasoning": None, "phases": None, "tool_calls": None, "tool_call_id": None},
    ]
    result = _parse_rows(rows)
    assert len(result) == 2
    assert result[0].role == "user"
    assert result[0].content == "[2025-01-01 10:00:00] hola"
    assert result[1].role == "assistant"
    assert result[1].content == "[2025-01-01 10:00:01] respuesta"


@pytest.mark.anyio
async def test_parse_rows_incomplete_row():
    rows = [
        {"role": "user", "content": "hola", "model": None, "created_at": "2025-01-01T10:00:00", "reasoning": None, "phases": None, "tool_calls": None, "tool_call_id": None},
    ]
    result = _parse_rows(rows)
    assert len(result) == 1
    assert result[0].role == "user"
    assert result[0].content == "[2025-01-01 10:00:00] hola"


@pytest.mark.anyio
async def test_sanitize_messages_assistant_with_tool_calls_no_content():
    tool_calls = [{"id": "tc1", "type": "function", "function": {"name": "web_search"}}]
    raw_msgs = [
        HistoryMessage(role="assistant", content=None, created_at="2025-01-01T10:00:00", tool_calls=tool_calls),
        HistoryMessage(role="tool", content="result", created_at="2025-01-01T10:00:01", tool_call_id="tc1"),
    ]
    result = _sanitize_messages(raw_msgs)
    assert len(result) == 2
    assert result[0].tool_calls == tool_calls


@pytest.mark.anyio
async def test_sanitize_messages_assistant_empty():
    raw_msgs = [
        HistoryMessage(role="assistant", content="", created_at="2025-01-01T10:00:00"),
    ]
    result = _sanitize_messages(raw_msgs)
    assert len(result) == 1
    assert result[0].role == "assistant"
    assert result[0].content == ""
