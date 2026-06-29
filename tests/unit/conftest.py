"""Shared test fixtures providing real lightweight implementations.

Use these fixtures to replace heavy mocking patterns in tests.
"""

from unittest.mock import AsyncMock

import pytest
import aiosqlite
import pytest_asyncio

from src.config_loader import Config
from src.memory.repos import (
    Repositories,
    MessageRepository,
    SessionRepository,
    ToolCallRepository,
    WidgetStateRepository,
    DebugRepository,
    SavedWidgetRepository,
    MemoryIndexRepository,
)
from src.core.services.history_service import HistoryService
from src.tools.registry import ToolRegistry


_SCHEMA_STATEMENTS = [
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


@pytest_asyncio.fixture
async def in_memory_db():
    """SQLite :memory: connection with full schema initialized.

    Each test gets a fresh isolated database.
    """
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    for stmt in _SCHEMA_STATEMENTS:
        await conn.execute(stmt)
    await conn.commit()

    yield conn

    await conn.close()


@pytest.fixture
def mock_conn():
    """Tuple of (conn, cursor) AsyncMocks for patched get_conn tests."""
    conn = AsyncMock()
    cursor = AsyncMock()
    conn.execute.return_value = cursor
    return conn, cursor


@pytest.fixture
def repos(in_memory_db):
    """Repository instances backed by the in-memory database."""
    return Repositories(
        messages=MessageRepository(conn=in_memory_db),
        sessions=SessionRepository(conn=in_memory_db),
        tool_calls=ToolCallRepository(conn=in_memory_db),
        widget_states=WidgetStateRepository(conn=in_memory_db),
        debug=DebugRepository(conn=in_memory_db),
        saved_widgets=SavedWidgetRepository(conn=in_memory_db),
        memory_index=MemoryIndexRepository(conn=in_memory_db),
    )


@pytest.fixture
def config():
    """Config dataclass with test-friendly defaults."""
    return Config(
        testing=True,
        environment="test",
        llm_provider="openai",
        llm_mode="go",
    )


@pytest.fixture
def tool_registry():
    """Empty ToolRegistry ready for test tool registration.

    Call ``registry.register(name, fn, definition)`` to add tools.
    The registry is pre-marked as built so property access won't
    trigger auto-discovery.
    """
    reg = ToolRegistry()
    reg._built = True
    return reg


@pytest.fixture
def history_service(repos):
    """Real HistoryService backed by in-memory repos."""
    return HistoryService(repos=repos)
