import json


from src.api.messages import save_message_record, get_session_messages
from src.api.session import ensure_session, rename_session, delete_session, get_sessions
from src.api.tools import get_tool_history
from src.api.debug import save_debug_info, get_debug_info
from src.memory.repos import ToolCallRepository
from src.memory.repos import MessageRecord


def save_message(
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
    return save_message_record(MessageRecord(
        session_id=session_id,
        role=role,
        content=content,
        model=model,
        reasoning=reasoning,
        phases=phases,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    ))


def test_save_and_get_message():
    sid = "test-session-1"
    ensure_session(sid)
    save_message(sid, "user", "hola", "test-model")
    save_message(sid, "assistant", "mundo", "test-model", reasoning="pensando")

    rows = get_session_messages(sid)
    assert len(rows) == 2
    assert rows[0][0] == "user"
    assert rows[0][1] == "hola"
    assert rows[1][0] == "assistant"
    assert rows[1][1] == "mundo"
    assert rows[1][4] == "pensando"


def test_history_ordering():
    sid = "test-ordering"
    ensure_session(sid)
    save_message(sid, "user", "a", "m")
    save_message(sid, "assistant", "b", "m")
    save_message(sid, "user", "c", "m")

    rows = get_session_messages(sid)
    assert len(rows) == 3
    assert rows[0][1] == "a"
    assert rows[1][1] == "b"
    assert rows[2][1] == "c"


def test_get_session_messages_limit():
    sid = "test-limit"
    ensure_session(sid)
    for i in range(10):
        save_message(sid, "user", f"msg-{i}", "m")
    rows = get_session_messages(sid, limit=3)
    assert len(rows) == 3


def test_session_crud():
    sid = "test-crud"
    ensure_session(sid)
    save_message(sid, "user", "hello", "m")
    sessions = get_sessions()
    assert any(s[0] == sid for s in sessions)

    rename_session(sid, "mi-chat")
    sessions = get_sessions()
    found = False
    for s in sessions:
        if s[0] == sid:
            assert s[5] == "mi-chat"
            found = True
            break
    assert found

    delete_session(sid)
    sessions = get_sessions()
    assert not any(s[0] == sid for s in sessions)


def test_tool_call_log():
    sid = "test-tools"
    ensure_session(sid)
    repo = ToolCallRepository()
    repo.log(sid, "web_search", '{"q":"test"}', "ok")
    repo.log(sid, "web_search", '{"q":"test2"}', "ok")

    rows = get_tool_history(sid)
    assert len(rows) == 2
    assert rows[0][0] == "web_search"
    assert rows[0][2] == "ok"


def test_debug_info():
    sid = "test-debug"
    ensure_session(sid)
    data = {
        "model": "big-pickle",
        "reasoning": "thinking...",
        "system_prompt": "you are...",
        "tool_calls": [{"name": "search", "status": "ok"}],
        "history_before": [{"role": "user", "content": "hi"}],
    }
    save_debug_info(sid, data)
    retrieved = get_debug_info(sid)
    assert retrieved["model"] == "big-pickle"
    assert retrieved["reasoning"] == "thinking..."
    assert len(retrieved["tool_calls"]) == 1
    assert retrieved["tool_calls"][0]["name"] == "search"


def test_empty_debug():
    assert get_debug_info("nonexistent") == {}


def test_save_message_default_reasoning():
    sid = "test-reasoning"
    ensure_session(sid)
    save_message(sid, "assistant", "ok", "m")
    rows = get_session_messages(sid)
    assert rows[0][4] == ""


def test_save_message_with_phases():
    sid = "test-phases"
    ensure_session(sid)
    phases = '[{"reasoning": "buscando", "tool_ids": ["c1"]}]'
    save_message(sid, "assistant", "resultado", "m", reasoning="pensando", phases=phases)
    rows = get_session_messages(sid)
    assert len(rows) == 1
    assert rows[0][4] == "pensando"
    assert json.loads(rows[0][5]) == [{"reasoning": "buscando", "tool_ids": ["c1"]}]


def test_get_sessions_empty():
    sessions = get_sessions()
    assert isinstance(sessions, list)


def test_delete_session_nonexistent():
    delete_session("no-existe")


def test_rename_session_empty_name():
    sid = "test-rename-empty"
    ensure_session(sid)
    save_message(sid, "user", "hola", "m")
    rename_session(sid, "")
    sessions = get_sessions()
    found = False
    for s in sessions:
        if s[0] == sid:
            assert s[5] == ""
            found = True
            break
    assert found


def test_tool_history_limit_exceeds():
    sid = "test-tool-limit"
    ensure_session(sid)
    repo = ToolCallRepository()
    for i in range(3):
        repo.log(sid, "web_search", f'{{"q":"test{i}"}}"', "ok", turn=i)
    rows = get_tool_history(sid, limit=100)
    assert len(rows) == 3
    assert rows[0][4] == 2


def test_log_tool_call_with_turn():
    sid = "test-turn"
    ensure_session(sid)
    repo = ToolCallRepository()
    repo.log(sid, "web_search", '{"q":"test"}', "ok", turn=42)
    rows = get_tool_history(sid)
    assert rows[0][4] == 42
