import os, sys, tempfile, json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MEMORY_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from src.memory import (
    init_db, save_message, get_history, get_session_messages,
    ensure_session, rename_session, delete_session, get_sessions,
    log_tool_call, get_tool_history,
    save_debug_info, get_debug_info,
)


def test_save_and_get_message():
    init_db()
    sid = "test-session-1"
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
    init_db()
    sid = "test-ordering"
    save_message(sid, "user", "a", "m")
    save_message(sid, "assistant", "b", "m")
    save_message(sid, "user", "c", "m")

    rows = get_session_messages(sid)
    assert len(rows) == 3
    assert rows[0][1] == "a"
    assert rows[1][1] == "b"
    assert rows[2][1] == "c"


def test_get_history_limit():
    init_db()
    sid = "test-limit"
    for i in range(10):
        save_message(sid, "user", f"msg-{i}", "m")
    rows = get_history(sid, limit=3)
    assert len(rows) == 3


def test_session_crud():
    init_db()
    sid = "test-crud"
    ensure_session(sid)
    # get_sessions only returns sessions with messages
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
    init_db()
    sid = "test-tools"
    log_tool_call(sid, "web_search", '{"q":"test"}', "ok")
    log_tool_call(sid, "web_search", '{"q":"test2"}', "ok")

    rows = get_tool_history(sid)
    assert len(rows) == 2
    assert rows[0][0] == "web_search"
    assert rows[0][2] == "ok"


def test_debug_info():
    init_db()
    sid = "test-debug"
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
    init_db()
    assert get_debug_info("nonexistent") == {}


def test_save_message_default_reasoning():
    init_db()
    sid = "test-reasoning"
    save_message(sid, "assistant", "ok", "m")
    rows = get_session_messages(sid)
    assert rows[0][4] == ""


def test_save_message_with_phases():
    init_db()
    sid = "test-phases"
    phases = '[{"reasoning": "buscando", "tool_ids": ["c1"]}]'
    save_message(sid, "assistant", "resultado", "m", reasoning="pensando", phases=phases)
    rows = get_session_messages(sid)
    assert len(rows) == 1
    assert rows[0][4] == "pensando"
    assert json.loads(rows[0][5]) == [{"reasoning": "buscando", "tool_ids": ["c1"]}]


def test_get_sessions_empty():
    init_db()
    sessions = get_sessions()
    assert isinstance(sessions, list)


def test_delete_session_nonexistent():
    init_db()
    delete_session("no-existe")
    # No debe lanzar error


def test_rename_session_empty_name():
    init_db()
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
    init_db()
    sid = "test-tool-limit"
    for i in range(3):
        log_tool_call(sid, "web_search", f'{{"q":"test{i}"}}"', "ok", turn=i)
    rows = get_tool_history(sid, limit=100)
    assert len(rows) == 3
    assert rows[0][4] == 2  # turn column


def test_log_tool_call_with_turn():
    init_db()
    sid = "test-turn"
    log_tool_call(sid, "web_search", '{"q":"test"}', "ok", turn=42)
    rows = get_tool_history(sid)
    assert rows[0][4] == 42
