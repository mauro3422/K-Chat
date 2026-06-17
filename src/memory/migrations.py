import sqlite3
from typing import Any


async def _migration_001_initial_schema(conn: Any, engine: Any) -> None:
    await engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    await engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            tool_name TEXT NOT NULL,
            input TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    await engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')
    await engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS debug_info (
            session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
            model TEXT,
            reasoning TEXT,
            system_prompt TEXT,
            tool_calls TEXT,
            history_before TEXT,
            asr_telemetry TEXT,
            updated_at TEXT NOT NULL
        )
    ''')
    await engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS widget_states (
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            widget_id TEXT NOT NULL,
            state TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id, widget_id)
        )
    ''')


async def _migration_002_add_reasoning(conn: Any, engine: Any) -> None:
    try:
        await engine.execute(conn, "ALTER TABLE messages ADD COLUMN reasoning TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass


async def _migration_003_add_tool_call_turn(conn: Any, engine: Any) -> None:
    try:
        await engine.execute(conn, "ALTER TABLE tool_calls ADD COLUMN turn INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


async def _migration_004_add_phases(conn: Any, engine: Any) -> None:
    try:
        await engine.execute(conn, "ALTER TABLE messages ADD COLUMN phases TEXT DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass


async def _migration_005_add_tool_calls(conn: Any, engine: Any) -> None:
    try:
        await engine.execute(conn, "ALTER TABLE messages ADD COLUMN tool_calls TEXT")
    except sqlite3.OperationalError:
        pass


async def _migration_006_add_tool_call_id(conn: Any, engine: Any) -> None:
    try:
        await engine.execute(conn, "ALTER TABLE messages ADD COLUMN tool_call_id TEXT")
    except sqlite3.OperationalError:
        pass


async def _migrate_old_schema(conn: Any, engine: Any) -> None:
    await engine.execute(conn, "ALTER TABLE saved_widgets RENAME TO saved_widgets_old")
    await engine.execute(conn, "ALTER TABLE widget_versions RENAME TO widget_versions_old")

    await engine.execute(conn, '''
        CREATE TABLE saved_widgets (
            widget_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            session_id TEXT REFERENCES sessions(session_id)
        )
    ''')
    await engine.execute(conn, '''
        CREATE TABLE widget_versions (
            widget_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            code TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            session_id TEXT REFERENCES sessions(session_id),
            PRIMARY KEY (widget_id, version)
        )
    ''')

    await engine.execute(conn, '''
        INSERT OR REPLACE INTO saved_widgets (widget_id, code, version, description, created_at, updated_at, session_id)
        SELECT widget_id, code, version, description, created_at, updated_at, session_id
        FROM saved_widgets_old
        ORDER BY version ASC
    ''')
    await engine.execute(conn, '''
        INSERT OR REPLACE INTO widget_versions (widget_id, version, code, description, created_at, session_id)
        SELECT widget_id, version, code, description, created_at, session_id
        FROM widget_versions_old
    ''')

    await engine.execute(conn, "DROP TABLE saved_widgets_old")
    await engine.execute(conn, "DROP TABLE widget_versions_old")


async def _create_fresh_schema(conn: Any, engine: Any) -> None:
    await engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS saved_widgets (
            widget_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            session_id TEXT REFERENCES sessions(session_id)
        )
    ''')
    await engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS widget_versions (
            widget_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            code TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            session_id TEXT REFERENCES sessions(session_id),
            PRIMARY KEY (widget_id, version)
        )
    ''')


async def _migration_007_saved_widgets_global(conn: Any, engine: Any) -> None:
    result = await engine.execute(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='saved_widgets'")
    table_exists = await result.fetchone()

    needs_migration = False
    if table_exists:
        result = await engine.execute(conn, "PRAGMA table_info(saved_widgets)")
        columns = await result.fetchall()
        for col in columns:
            if col["name"] == 'session_id' and col["pk"] > 0:
                needs_migration = True
                break

    if needs_migration:
        await _migrate_old_schema(conn, engine)
    else:
        await _create_fresh_schema(conn, engine)


async def _migration_008_add_token_counts(conn: Any, engine: Any) -> None:
    try:
        await engine.execute(conn, "ALTER TABLE messages ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        await engine.execute(conn, "ALTER TABLE messages ADD COLUMN completion_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        await engine.execute(conn, "ALTER TABLE messages ADD COLUMN total_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


async def _migration_009_add_indexes(conn: Any, engine: Any) -> None:
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id)")
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_tool_calls_session_id ON tool_calls (session_id)")
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_saved_widgets_session_id ON saved_widgets (session_id)")
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_widget_versions_session_id ON widget_versions (session_id)")


async def _migration_010_memory_index(conn, engine):
    await engine.execute(conn, """
        CREATE TABLE IF NOT EXISTS memory_index (
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (session_id, key)
        )
    """)
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_memory_index_key ON memory_index (key)")


async def _migration_011_cleanup_orphans(conn, engine):
    # Clean orphaned records from sessions that were deleted.
    # Skip tables that have been migrated to global schema (no session_id column).
    for table in ('widget_states', 'messages', 'tool_calls', 'debug_info', 'memory_index'):
        try:
            await engine.execute(conn, f"""
                DELETE FROM {table} WHERE session_id NOT IN (SELECT session_id FROM sessions)
            """)
        except Exception:
            # Table may have been converted to global schema (memory_index)
            # or column doesn't exist — skip gracefully.
            pass
    # Add cleanup triggers: when a session is deleted, cascade cleanups
    triggers = [
        ('trg_cleanup_widget_states', 'widget_states'),
        ('trg_cleanup_memory_index', 'memory_index'),
        ('trg_cleanup_messages', 'messages'),
        ('trg_cleanup_tool_calls', 'tool_calls'),
        ('trg_cleanup_debug_info', 'debug_info'),
    ]
    for tname, table in triggers:
        await engine.execute(conn, f"""
            CREATE TRIGGER IF NOT EXISTS {tname}
            AFTER DELETE ON sessions
            BEGIN
                DELETE FROM {table} WHERE session_id = OLD.session_id;
            END;
        """)


async def _migration_012_add_asr_telemetry(conn, engine):
    try:
        await engine.execute(conn, "ALTER TABLE debug_info ADD COLUMN asr_telemetry TEXT")
    except sqlite3.OperationalError:
        pass


async def _migration_013_composite_tool_index(conn: Any, engine: Any) -> None:
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_tool_calls_session_created ON tool_calls (session_id, created_at DESC)")


async def _migration_014_gateway_log(conn: Any, engine: Any) -> None:
    await engine.execute(conn, """
        CREATE TABLE IF NOT EXISTS gateway_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (datetime('now')),
            level TEXT NOT NULL,
            service TEXT NOT NULL,
            event TEXT NOT NULL,
            detail TEXT DEFAULT '',
            pid INTEGER,
            meta TEXT DEFAULT '{}'
        )
    """)
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_gateway_log_ts ON gateway_log (ts DESC)")
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_gateway_log_service ON gateway_log (service, ts DESC)")


async def _migration_015_chat_journal(conn: Any, engine: Any) -> None:
    await engine.execute(conn, """
        CREATE TABLE IF NOT EXISTS chat_journal (
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
        )
    """)
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_chat_journal_session ON chat_journal (session_id, ts DESC)")
    await engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_chat_journal_ts ON chat_journal (ts DESC)")


async def _migration_016_telegram_msg_ids(conn: Any, engine: Any) -> None:
    """Persist Telegram message IDs so they survive bot restarts."""
    await engine.execute(conn, """
        CREATE TABLE IF NOT EXISTS telegram_msg_ids (
            chat_id INTEGER NOT NULL,
            phase_key TEXT NOT NULL,
            msg_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (chat_id, phase_key)
        )
    """)
    await engine.execute(conn, """
        CREATE INDEX IF NOT EXISTS idx_telegram_msg_ids_chat
        ON telegram_msg_ids (chat_id)
    """)


async def _migration_017_telegram_chat_id(conn: Any, engine: Any) -> None:
    """Add telegram_chat_id column to sessions for reliable lookup."""
    try:
        await engine.execute(conn, """
            ALTER TABLE sessions ADD COLUMN telegram_chat_id INTEGER
        """)
    except sqlite3.OperationalError:
        pass  # Already exists
    try:
        await engine.execute(conn, """
            CREATE INDEX IF NOT EXISTS idx_sessions_telegram_chat_id
            ON sessions (telegram_chat_id)
        """)
    except Exception:
        pass


async def _migration_018_auto_memories(conn: Any, engine: Any) -> None:
    """Add auto_memories column to debug_info table."""
    try:
        await engine.execute(conn, "ALTER TABLE debug_info ADD COLUMN auto_memories TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass  # Column already exists


async def _migration_019_memory_index_weight(conn: Any, engine: Any) -> None:
    """Add weight column to memory_index in sessions.db."""
    try:
        await engine.execute(conn, "ALTER TABLE memory_index ADD COLUMN weight REAL NOT NULL DEFAULT 1.0")
    except Exception:
        pass


async def _migration_020_chat_journal_fk(conn: Any, engine: Any) -> None:
    """Add cascade cleanup trigger for chat_journal when session is deleted.

    chat_journal was created in _migration_015 without a FK constraint,
    so orphaned rows accumulate when sessions are deleted. This trigger
    mirrors _migration_011's pattern for other session-scoped tables.
    """
    await engine.execute(conn, """
        CREATE TRIGGER IF NOT EXISTS trg_cleanup_chat_journal
        AFTER DELETE ON sessions
        BEGIN
            DELETE FROM chat_journal WHERE session_id = OLD.session_id;
        END;
    """)


async def _migration_021_messages_session_created_index(conn: Any, engine: Any) -> None:
    """Add composite index on (session_id, created_at) for session listing performance.

    The get_all query does:
        GROUP BY m.session_id ORDER BY MAX(m.created_at) DESC

    A composite index covers both the GROUP BY and the ORDER BY without a filesort.
    """
    await engine.execute(conn, """
        CREATE INDEX IF NOT EXISTS idx_messages_session_created
        ON messages (session_id, created_at)
    """)


MIGRATIONS = (
    _migration_001_initial_schema,
    _migration_002_add_reasoning,
    _migration_003_add_tool_call_turn,
    _migration_004_add_phases,
    _migration_005_add_tool_calls,
    _migration_006_add_tool_call_id,
    _migration_007_saved_widgets_global,
    _migration_008_add_token_counts,
    _migration_009_add_indexes,
    _migration_010_memory_index,
    _migration_011_cleanup_orphans,
    _migration_012_add_asr_telemetry,
    _migration_013_composite_tool_index,
    _migration_014_gateway_log,
    _migration_015_chat_journal,
    _migration_016_telegram_msg_ids,
    _migration_017_telegram_chat_id,
    _migration_018_auto_memories,
    _migration_019_memory_index_weight,
    _migration_020_chat_journal_fk,
    _migration_021_messages_session_created_index,
)
