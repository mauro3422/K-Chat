import sqlite3
from typing import Any


def _migration_001_initial_schema(conn: Any, engine: Any) -> None:
    engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            tool_name TEXT NOT NULL,
            input TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')
    engine.execute(conn, '''
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
    engine.execute(conn, '''
        CREATE TABLE IF NOT EXISTS widget_states (
            session_id TEXT NOT NULL REFERENCES sessions(session_id),
            widget_id TEXT NOT NULL,
            state TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_id, widget_id)
        )
    ''')


def _migration_002_add_reasoning(conn: Any, engine: Any) -> None:
    try:
        engine.execute(conn, "ALTER TABLE messages ADD COLUMN reasoning TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass


def _migration_003_add_tool_call_turn(conn: Any, engine: Any) -> None:
    try:
        engine.execute(conn, "ALTER TABLE tool_calls ADD COLUMN turn INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_004_add_phases(conn: Any, engine: Any) -> None:
    try:
        engine.execute(conn, "ALTER TABLE messages ADD COLUMN phases TEXT DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass


def _migration_005_add_tool_calls(conn: Any, engine: Any) -> None:
    try:
        engine.execute(conn, "ALTER TABLE messages ADD COLUMN tool_calls TEXT")
    except sqlite3.OperationalError:
        pass


def _migration_006_add_tool_call_id(conn: Any, engine: Any) -> None:
    try:
        engine.execute(conn, "ALTER TABLE messages ADD COLUMN tool_call_id TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_old_schema(conn: Any, engine: Any) -> None:
    engine.execute(conn, "ALTER TABLE saved_widgets RENAME TO saved_widgets_old")
    engine.execute(conn, "ALTER TABLE widget_versions RENAME TO widget_versions_old")

    engine.execute(conn, '''
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
    engine.execute(conn, '''
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

    engine.execute(conn, '''
        INSERT OR REPLACE INTO saved_widgets (widget_id, code, version, description, created_at, updated_at, session_id)
        SELECT widget_id, code, version, description, created_at, updated_at, session_id
        FROM saved_widgets_old
        ORDER BY version ASC
    ''')
    engine.execute(conn, '''
        INSERT OR REPLACE INTO widget_versions (widget_id, version, code, description, created_at, session_id)
        SELECT widget_id, version, code, description, created_at, session_id
        FROM widget_versions_old
    ''')

    engine.execute(conn, "DROP TABLE saved_widgets_old")
    engine.execute(conn, "DROP TABLE widget_versions_old")


def _create_fresh_schema(conn: Any, engine: Any) -> None:
    engine.execute(conn, '''
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
    engine.execute(conn, '''
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


def _migration_007_saved_widgets_global(conn: Any, engine: Any) -> None:
    result = engine.execute(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='saved_widgets'")
    table_exists = result.fetchone()

    needs_migration = False
    if table_exists:
        result = engine.execute(conn, "PRAGMA table_info(saved_widgets)")
        columns = result.fetchall()
        for col in columns:
            if col["name"] == 'session_id' and col["pk"] > 0:
                needs_migration = True
                break

    if needs_migration:
        _migrate_old_schema(conn, engine)
    else:
        _create_fresh_schema(conn, engine)


def _migration_008_add_token_counts(conn: Any, engine: Any) -> None:
    try:
        engine.execute(conn, "ALTER TABLE messages ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        engine.execute(conn, "ALTER TABLE messages ADD COLUMN completion_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        engine.execute(conn, "ALTER TABLE messages ADD COLUMN total_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_009_add_indexes(conn: Any, engine: Any) -> None:
    engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id)")
    engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_tool_calls_session_id ON tool_calls (session_id)")
    engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_saved_widgets_session_id ON saved_widgets (session_id)")
    engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_widget_versions_session_id ON widget_versions (session_id)")


def _migration_010_memory_index(conn, engine):
    engine.execute(conn, """
        CREATE TABLE IF NOT EXISTS memory_index (
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (session_id, key)
        )
    """)
    engine.execute(conn, "CREATE INDEX IF NOT EXISTS idx_memory_index_key ON memory_index (key)")


def _migration_011_cleanup_orphans(conn, engine):
    # Clean orphaned records from sessions that were deleted
    for table in ('widget_states', 'memory_index', 'messages', 'tool_calls', 'debug_info'):
        engine.execute(conn, f"""
            DELETE FROM {table} WHERE session_id NOT IN (SELECT session_id FROM sessions)
        """)
    # Add cleanup triggers: when a session is deleted, cascade cleanups
    triggers = [
        ('trg_cleanup_widget_states', 'widget_states'),
        ('trg_cleanup_memory_index', 'memory_index'),
        ('trg_cleanup_messages', 'messages'),
        ('trg_cleanup_tool_calls', 'tool_calls'),
        ('trg_cleanup_debug_info', 'debug_info'),
    ]
    for tname, table in triggers:
        engine.execute(conn, f"""
            CREATE TRIGGER IF NOT EXISTS {tname}
            AFTER DELETE ON sessions
            BEGIN
                DELETE FROM {table} WHERE session_id = OLD.session_id;
            END;
        """)


def _migration_012_add_asr_telemetry(conn, engine):
    try:
        engine.execute(conn, "ALTER TABLE debug_info ADD COLUMN asr_telemetry TEXT")
    except sqlite3.OperationalError:
        pass


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
)
