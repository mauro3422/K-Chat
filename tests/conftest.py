import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set temp DB paths BEFORE any module that imports config_loader.py is loaded.
# This ensures test DB isolation regardless of .env settings.
# NOTE: the actual env vars read by the code are SESSIONS_DB_PATH (for sessions.db)
# and KAIROS_MEMORY_DB_PATH (for memory.db), NOT "MEMORY_DB_PATH".
_TEST_WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER", "main")
_TEST_TMP = tempfile.gettempdir()
os.environ["SESSIONS_DB_PATH"] = os.path.join(_TEST_TMP, f"kairos_test_{_TEST_WORKER_ID}_sessions.db")
os.environ["KAIROS_MEMORY_DB_PATH"] = os.path.join(_TEST_TMP, f"kairos_test_{_TEST_WORKER_ID}_memory.db")
os.environ["KAIROS_MEMORY_WRITE_QUEUE_PATH"] = os.path.join(_TEST_TMP, f"kairos_test_{_TEST_WORKER_ID}_memory_write_queue.json")
os.environ["OPENCODE_ZEN_API_KEY"] = "test-key-for-tests"
os.environ["SEARXNG_AUTO_START"] = "false"
os.environ["TESTING"] = "true"

import json
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

_SESSIONS_SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(session_id),
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        model TEXT,
        reasoning TEXT DEFAULT '',
        phases TEXT DEFAULT '[]',
        tool_calls TEXT,
        tool_call_id TEXT,
        prompt_tokens INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tool_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(session_id),
        tool_name TEXT NOT NULL,
        input TEXT NOT NULL,
        status TEXT NOT NULL,
        turn INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS debug_info (
        session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
        model TEXT,
        reasoning TEXT,
        system_prompt TEXT,
        tool_calls TEXT,
        history_before TEXT,
        asr_telemetry TEXT,
        auto_memories TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS widget_states (
        session_id TEXT NOT NULL REFERENCES sessions(session_id),
        widget_id TEXT NOT NULL,
        state TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (session_id, widget_id)
    )""",
    """CREATE TABLE IF NOT EXISTS saved_widgets (
        widget_id TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        description TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        session_id TEXT REFERENCES sessions(session_id)
    )""",
    """CREATE TABLE IF NOT EXISTS widget_versions (
        widget_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        code TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        session_id TEXT REFERENCES sessions(session_id),
        PRIMARY KEY (widget_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS memory_index (
        session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        value TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (session_id, key)
    )""",
    """CREATE TABLE IF NOT EXISTS gateway_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now')),
        level TEXT NOT NULL,
        service TEXT NOT NULL,
        event TEXT NOT NULL,
        detail TEXT DEFAULT '',
        pid INTEGER,
        meta TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS chat_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now')),
        session_id TEXT NOT NULL,
        user_msg TEXT DEFAULT '',
        assistant_msg TEXT DEFAULT '',
        tools_used TEXT DEFAULT '[]',
        model TEXT DEFAULT '',
        duration_ms INTEGER DEFAULT 0,
        token_count INTEGER DEFAULT 0,
        error TEXT DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_session_id ON tool_calls (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_saved_widgets_session_id ON saved_widgets (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_widget_versions_session_id ON widget_versions (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_index_key ON memory_index (key)",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_session_created ON tool_calls (session_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_gateway_log_ts ON gateway_log (ts DESC)",
    "CREATE INDEX IF NOT EXISTS idx_gateway_log_service ON gateway_log (service, ts DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_journal_session ON chat_journal (session_id, ts DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_journal_ts ON chat_journal (ts DESC)",
]


@pytest.fixture
def make_choice():
    """Build a mock ChatCompletion Choice."""
    def _make(content=None, finish_reason="stop", tool_calls=None, reasoning_content=None):
        msg = MagicMock()
        msg.content = content
        msg.reasoning_content = reasoning_content
        if tool_calls:
            tcs = []
            for tc in tool_calls:
                mock_tc = MagicMock()
                mock_tc.id = tc.get("id", "call_1")
                mock_tc.function.name = tc["name"]
                mock_tc.function.arguments = json.dumps(tc.get("args", {}))
                tcs.append(mock_tc)
            msg.tool_calls = tcs
        else:
            msg.tool_calls = None
        choice = MagicMock()
        choice.message = msg
        choice.finish_reason = finish_reason
        return choice
    return _make


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db(monkeypatch):
    """Fixture that isolates all databases during tests.

    Creates temp dirs for sessions.db AND memory.db, sets the correct
    env vars (``SESSIONS_DB_PATH`` and ``KAIROS_MEMORY_DB_PATH``), and
    cleans up both on teardown.

    NOTE: The old code used ``MEMORY_DB_PATH`` which is NOT read by
    any module — the correct env vars are ``SESSIONS_DB_PATH`` (for
    `db_path.py`) and ``KAIROS_MEMORY_DB_PATH`` (for `memory_db_path.py`).
    """
    temp_dir = tempfile.mkdtemp()
    sessions_db_path = os.path.join(temp_dir, "test_sessions.db")
    memory_db_path = os.path.join(temp_dir, "test_memory.db")
    memory_queue_path = os.path.join(temp_dir, "test_memory_write_queue.json")

    monkeypatch.setenv("SESSIONS_DB_PATH", sessions_db_path)
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", memory_db_path)
    monkeypatch.setenv("KAIROS_MEMORY_WRITE_QUEUE_PATH", memory_queue_path)

    conn = sqlite3.connect(sessions_db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for statement in _SESSIONS_SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()

    yield sessions_db_path

    try:
        from src.api.lifecycle import reset_runtime_state_async
        await reset_runtime_state_async()
    except Exception:
        pass

    try:
        for path in (sessions_db_path, memory_db_path, memory_queue_path):
            if os.path.exists(path):
                os.remove(path)
        os.rmdir(temp_dir)
    except Exception:
        pass


@pytest_asyncio.fixture(autouse=True)
async def reset_shared_runtime_state():
    """Keep process-local singletons isolated between tests."""
    try:
        from src.api.lifecycle import reset_runtime_state_async
        await reset_runtime_state_async()
    except Exception:
        pass

    try:
        from web.app_factory import reset_web_runtime_state
        reset_web_runtime_state()
    except Exception:
        pass

    yield

    try:
        from src.api.lifecycle import reset_runtime_state_async
        await reset_runtime_state_async()
    except Exception:
        pass

    try:
        from web.app_factory import reset_web_runtime_state
        reset_web_runtime_state()
    except Exception:
        pass
