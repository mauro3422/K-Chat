import pytest
from unittest.mock import AsyncMock
import json
import re

from src.api.messages import save_message_record
from src.memory.repos import MessageRecord, get_repos
from src.api.session import ensure_session
from src.core.history_rebuilder import rebuild_history
import os

from src.memory.conn_factory import configure_connection, create_raw_conn
from src.memory.db_path import resolve_db_path


async def init_db():
    db_path = resolve_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = await create_raw_conn(db_path)
    await configure_connection(conn)
    cursor = await conn.cursor()
    await cursor.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
    await cursor.execute("SELECT MAX(version) AS version FROM schema_version")
    row = await cursor.fetchone()
    if row is None or row["version"] is None:
        await cursor.execute("INSERT INTO schema_version (version) VALUES (0)")
    await conn.commit()
    await conn.close()
    from src.memory.schema import init_db_for_path
    await init_db_for_path(db_path)


async def save_message(
    session_id,
    role,
    content,
    model,
    reasoning="",
    phases="[]",
    tool_calls=None,
    tool_call_id=None,
    **kwargs,
):
    return await save_message_record(MessageRecord(
        session_id=session_id,
        role=role,
        content=content,
        model=model,
        reasoning=reasoning,
        phases=phases,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    ), repos=get_repos())


@pytest.mark.anyio
async def test_rebuild_history_empty_session():
    session_id = "test-empty-session"
    await init_db()
    await ensure_session(session_id)
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 1
    assert result[0]["role"] == "system"
    assert "test-model" in result[0]["content"]


@pytest.mark.anyio
async def test_rebuild_history_simple():
    session_id = "test-simple"
    await init_db()
    await ensure_session(session_id)
    await save_message(session_id=session_id, role="user", content="Hello", model="test-model")
    await save_message(session_id=session_id, role="assistant", content="Hi there!", model="test-model")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 3
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert re.match(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Hello", result[1]["content"])
    assert result[2]["role"] == "assistant"
    assert re.match(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Hi there!", result[2]["content"])


@pytest.mark.anyio
async def test_rebuild_history_tool_calls_with_responses():
    session_id = "test-tool-with-response"
    await init_db()
    await ensure_session(session_id)
    tool_calls_json = json.dumps([
        {"id": "call_weather", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
        {"id": "call_time", "type": "function", "function": {"name": "get_time", "arguments": "{}"}},
    ])
    await save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    await save_message(session_id=session_id, role="tool", content='{"temp": 22}', model="test-model", tool_call_id="call_weather")
    await save_message(session_id=session_id, role="tool", content='{"time": "12:00"}', model="test-model", tool_call_id="call_time")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 4
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "assistant"
    assert result[1]["tool_calls"] == [
        {"id": "call_weather", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
        {"id": "call_time", "type": "function", "function": {"name": "get_time", "arguments": "{}"}},
    ]
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "call_weather"
    assert result[3]["role"] == "tool"
    assert result[3]["tool_call_id"] == "call_time"


@pytest.mark.anyio
async def test_rebuild_history_orphan_tool_calls():
    session_id = "test-orphan-tc"
    await init_db()
    await ensure_session(session_id)
    tool_calls_json = json.dumps([
        {"id": "call_orphan", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
    ])
    await save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 1
    assert result[0]["role"] == "system"


@pytest.mark.anyio
async def test_rebuild_history_orphan_tool_response():
    session_id = "test-orphan-tool-resp"
    await init_db()
    await ensure_session(session_id)
    await save_message(session_id=session_id, role="tool", content="orphan result", model="test-model", tool_call_id="call_nonexistent")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 1
    assert result[0]["role"] == "system"


@pytest.mark.anyio
async def test_rebuild_history_orphan_tool_calls_with_content_kept():
    session_id = "test-orphan-tc-with-content"
    await init_db()
    await ensure_session(session_id)
    tool_calls_json = json.dumps([
        {"id": "call_orphan", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
    ])
    await save_message(session_id=session_id, role="assistant", content="I have content even without tools", model="test-model", tool_calls=tool_calls_json)
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 2
    assert result[1]["role"] == "assistant"
    assert "tool_calls" not in result[1]
    assert "I have content even without tools" in result[1]["content"]


@pytest.mark.anyio
async def test_rebuild_history_reasoning():
    session_id = "test-reasoning"
    await init_db()
    await ensure_session(session_id)
    await save_message(session_id=session_id, role="user", content="Think step by step", model="test-model")
    await save_message(session_id=session_id, role="assistant", content="Final answer", model="test-model", reasoning="Let me think...")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 3
    assert result[2]["role"] == "assistant"
    assert result[2]["reasoning_content"] == "Let me think..."
    assert result[2]["content"].endswith("Final answer")


@pytest.mark.anyio
async def test_rebuild_history_multiple_timestamps():
    session_id = "test-timestamps"
    await init_db()
    await ensure_session(session_id)
    await save_message(session_id=session_id, role="user", content="First", model="test-model")
    await save_message(session_id=session_id, role="assistant", content="Second", model="test-model")
    await save_message(session_id=session_id, role="user", content="Third", model="test-model")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 4
    for i in range(1, 4):
        assert result[i]["content"].startswith("["), f"msg {i} missing timestamp: {result[i]['content']}"
    assert result[1]["content"].endswith("First")
    assert result[2]["content"].endswith("Second")
    assert result[3]["content"].endswith("Third")
    ts1 = re.match(r"\[(.+?)\]", result[1]["content"]).group(1)
    ts2 = re.match(r"\[(.+?)\]", result[2]["content"]).group(1)
    ts3 = re.match(r"\[(.+?)\]", result[3]["content"]).group(1)
    assert ts1 <= ts2 <= ts3


@pytest.mark.anyio
async def test_rebuild_history_skips_system_rows():
    session_id = "test-skip-system"
    await init_db()
    await ensure_session(session_id)
    await save_message(session_id=session_id, role="system", content="this should be ignored", model="test-model")
    await save_message(session_id=session_id, role="user", content="Hello", model="test-model")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert "this should be ignored" not in result[0]["content"]
    assert result[1]["role"] == "user"
    assert result[1]["content"].endswith("Hello")


@pytest.mark.anyio
async def test_rebuild_history_content_none_with_tool_calls():
    session_id = "test-content-none-tc"
    await init_db()
    await ensure_session(session_id)
    tool_calls_json = json.dumps([
        {"id": "call_none", "type": "function", "function": {"name": "do_something", "arguments": "{}"}},
    ])
    await save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    await save_message(session_id=session_id, role="tool", content="done", model="test-model", tool_call_id="call_none")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 3
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] is None
    assert result[1]["tool_calls"] == [
        {"id": "call_none", "type": "function", "function": {"name": "do_something", "arguments": "{}"}},
    ]
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "call_none"


@pytest.mark.anyio
async def test_rebuild_history_partial_tool_calls_filtered():
    session_id = "test-partial-tc"
    await init_db()
    await ensure_session(session_id)
    tool_calls_json = json.dumps([
        {"id": "call_matched", "type": "function", "function": {"name": "matched_func", "arguments": "{}"}},
        {"id": "call_orphan", "type": "function", "function": {"name": "orphan_func", "arguments": "{}"}},
    ])
    await save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    await save_message(session_id=session_id, role="tool", content="matched result", model="test-model", tool_call_id="call_matched")
    from src.memory.repos import get_repos
    result = await rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    assert len(result) == 3
    assert result[1]["role"] == "assistant"
    assert len(result[1]["tool_calls"]) == 1
    assert result[1]["tool_calls"][0]["id"] == "call_matched"
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "call_matched"
