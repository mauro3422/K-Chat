"""Tests for db_query tool."""
import os
import sqlite3
import pytest
from pathlib import Path

# Set test DB path before importing tool
# NOTE: uses SESSIONS_DB_PATH (not MEMORY_DB_PATH) — that's the var
# that db_path.py / db_query tool actually read.
TEST_DB = "/tmp/kchat_test_db_query.db"
os.environ["SESSIONS_DB_PATH"] = TEST_DB

import importlib.util
spec = importlib.util.spec_from_file_location("db_query", "skills/db-query/tool.py")
db_query = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db_query)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Initialize test DB with schema before each test."""
    # Remove old DB
    if os.path.exists(TEST_DB):
        os.unlink(TEST_DB)
    
    # Create DB with required tables
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Create schema_version
    cur.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
    cur.execute("INSERT INTO schema_version (version) VALUES (1)")
    
    # Create sessions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create messages table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model TEXT
        )
    """)
    
    # Create tool_calls table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            tool_name TEXT,
            status TEXT,
            turn INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create other required tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_widgets (
            widget_id TEXT PRIMARY KEY,
            version INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS widget_states (
            session_id TEXT,
            widget_id TEXT,
            state TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS debug_info (
            session_id TEXT,
            model TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_index (
            session_id TEXT,
            key TEXT,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS widget_versions (
            widget_id TEXT,
            version INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert test data
    cur.execute("INSERT INTO sessions (session_id, name) VALUES ('test-session-1', 'Test Session')")
    cur.execute("INSERT INTO sessions (session_id, name) VALUES ('test-session-2', 'Another Session')")
    
    cur.execute("INSERT INTO messages (session_id, role, content, model) VALUES ('test-session-1', 'user', 'Hello world', 'test-model')")
    cur.execute("INSERT INTO messages (session_id, role, content, model) VALUES ('test-session-1', 'assistant', 'Hi there!', 'test-model')")
    cur.execute("INSERT INTO messages (session_id, role, content, model) VALUES ('test-session-2', 'user', 'Another message', 'test-model')")
    
    conn.commit()
    conn.close()
    
    yield
    
    # Cleanup after tests
    if os.path.exists(TEST_DB):
        os.unlink(TEST_DB)


class TestDbQuery:
    @pytest.mark.anyio
    async def test_query_messages_table(self):
        """Test querying messages table returns expected data."""
        result = await db_query.run(table="messages")
        assert "messages" in result.lower() or "📊" in result
        assert "Hello world" in result or "user" in result
    
    @pytest.mark.anyio
    async def test_query_sessions_table(self):
        """Test querying sessions table returns expected data."""
        result = await db_query.run(table="sessions")
        assert "sessions" in result.lower() or "📊" in result
        assert "test-session-1" in result or "Test Session" in result
    
    @pytest.mark.anyio
    async def test_query_with_session_id_filter(self):
        """Test filtering by session_id."""
        result = await db_query.run(table="messages", session_id="test-session-1")
        assert "Hello world" in result
        assert "Another message" not in result
    
    @pytest.mark.anyio
    async def test_invalid_table_name(self):
        """Test querying invalid table returns error."""
        result = await db_query.run(table="nonexistent_table")
        assert "[ERROR]" in result
        assert "no permitida" in result
    
    @pytest.mark.anyio
    async def test_empty_result(self):
        """Test query that returns no results."""
        result = await db_query.run(table="messages", session_id="nonexistent-session")
        assert "Sin resultados" in result
    
    @pytest.mark.anyio
    async def test_limit_parameter(self):
        """Test limit parameter works."""
        result = await db_query.run(table="messages", limit=1)
        # Should show only 1 row
        assert "1 filas" in result
    
    @pytest.mark.anyio
    async def test_invalid_table_injection(self):
        """Test SQL injection attempt in table name."""
        result = await db_query.run(table="messages; DROP TABLE sessions;--")
        assert "[ERROR]" in result