import pytest
from unittest.mock import AsyncMock
import json


from src.api.messages import save_message_record, get_session_messages
from src.api.session import ensure_session, rename_session, delete_session, get_sessions
from src.api.tools import get_tool_history
from src.api.debug import save_debug_info, get_debug_info
from src.memory.repos import ToolCallRepository
from src.memory.repos import MessageRecord, get_repos


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
async def test_save_and_get_message():
    sid = "test-session-1"
    await ensure_session(sid)
    await save_message(sid, "user", "hola", "test-model")
    await save_message(sid, "assistant", "mundo", "test-model", reasoning="pensando")

    rows = await get_session_messages(sid, repos=get_repos())
    assert len(rows) == 2
    assert rows[0][0] == "user"
    assert rows[0][1] == "hola"
    assert rows[1][0] == "assistant"
    assert rows[1][1] == "mundo"
    assert rows[1][4] == "pensando"


@pytest.mark.anyio
async def test_history_ordering():
    sid = "test-ordering"
    await ensure_session(sid)
    await save_message(sid, "user", "a", "m")
    await save_message(sid, "assistant", "b", "m")
    await save_message(sid, "user", "c", "m")

    rows = await get_session_messages(sid, repos=get_repos())
    assert len(rows) == 3
    assert rows[0][1] == "a"
    assert rows[1][1] == "b"
    assert rows[2][1] == "c"


@pytest.mark.anyio
async def test_get_session_messages_limit():
    sid = "test-limit"
    await ensure_session(sid)
    for i in range(10):
        await save_message(sid, "user", f"msg-{i}", "m")
    rows = await get_session_messages(sid, limit=3, repos=get_repos())
    assert len(rows) == 3


@pytest.mark.anyio
async def test_session_crud():
    sid = "test-crud"
    await ensure_session(sid)
    await save_message(sid, "user", "hello", "m")
    sessions = await get_sessions()
    assert any(s[0] == sid for s in sessions)

    await rename_session(sid, "mi-chat")
    sessions = await get_sessions()
    found = False
    for s in sessions:
        if s[0] == sid:
            assert s[5] == "mi-chat"
            found = True
            break
    assert found

    await delete_session(sid, repos=get_repos())
    sessions = await get_sessions()
    assert not any(s[0] == sid for s in sessions)


@pytest.mark.anyio
async def test_tool_call_log():
    sid = "test-tools"
    await ensure_session(sid)
    repo = ToolCallRepository()
    await repo.log(sid, "web_search", '{"q":"test"}', "ok")
    await repo.log(sid, "web_search", '{"q":"test2"}', "ok")

    rows = await get_tool_history(sid, repos=get_repos())
    assert len(rows) == 2
    assert rows[0][0] == "web_search"
    assert rows[0][2] == "ok"


@pytest.mark.anyio
async def test_debug_info():
    sid = "test-debug"
    await ensure_session(sid)
    data = {
        "model": "big-pickle",
        "reasoning": "thinking...",
        "system_prompt": "you are...",
        "tool_calls": [{"name": "search", "status": "ok"}],
        "history_before": [{"role": "user", "content": "hi"}],
    }
    await save_debug_info(sid, data)
    retrieved = await get_debug_info(sid)
    assert retrieved["model"] == "big-pickle"
    assert retrieved["reasoning"] == "thinking..."
    assert len(retrieved["tool_calls"]) == 1
    assert retrieved["tool_calls"][0]["name"] == "search"


@pytest.mark.anyio
async def test_empty_debug():
    assert await get_debug_info("nonexistent") == {}


@pytest.mark.anyio
async def test_save_message_default_reasoning():
    sid = "test-reasoning"
    await ensure_session(sid)
    await save_message(sid, "assistant", "ok", "m")
    rows = await get_session_messages(sid, repos=get_repos())
    assert rows[0][4] == ""


@pytest.mark.anyio
async def test_save_message_with_phases():
    sid = "test-phases"
    await ensure_session(sid)
    phases = '[{"reasoning": "buscando", "tool_ids": ["c1"]}]'
    await save_message(sid, "assistant", "resultado", "m", reasoning="pensando", phases=phases)
    rows = await get_session_messages(sid, repos=get_repos())
    assert len(rows) == 1
    assert rows[0][4] == "pensando"
    assert json.loads(rows[0][5]) == [{"reasoning": "buscando", "tool_ids": ["c1"]}]


@pytest.mark.anyio
async def test_get_sessions_empty():
    sessions = await get_sessions()
    assert isinstance(sessions, list)


@pytest.mark.anyio
async def test_delete_session_nonexistent():
    await delete_session("no-existe", repos=get_repos())


@pytest.mark.anyio
async def test_rename_session_empty_name():
    sid = "test-rename-empty"
    await ensure_session(sid)
    await save_message(sid, "user", "hola", "m")
    await rename_session(sid, "")
    sessions = await get_sessions()
    found = False
    for s in sessions:
        if s[0] == sid:
            assert s[5] == ""
            found = True
            break
    assert found


@pytest.mark.anyio
async def test_tool_history_limit_exceeds():
    sid = "test-tool-limit"
    await ensure_session(sid)
    repo = ToolCallRepository()
    for i in range(3):
        await repo.log(sid, "web_search", f'{{"q":"test{i}"}}"', "ok", turn=i)
    rows = await get_tool_history(sid, limit=100, repos=get_repos())
    assert len(rows) == 3
    assert rows[0][4] == 2


@pytest.mark.anyio
async def test_log_tool_call_with_turn():
    sid = "test-turn"
    await ensure_session(sid)
    repo = ToolCallRepository()
    await repo.log(sid, "web_search", '{"q":"test"}', "ok", turn=42)
    rows = await get_tool_history(sid, repos=get_repos())
    assert rows[0][4] == 42
