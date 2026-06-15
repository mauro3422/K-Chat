"""Schema and migrations for memory.db (curated, syncable memory).

Uses synchronous sqlite3 for initialization to avoid aiosqlite thread
issues when creating a new connection after closing a previous one.
"""

import logging
import os
import sqlite3

from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.migration_runner import run_pending_migrations
from src.memory.lifecycle import mark_initialized

logger = logging.getLogger(__name__)


def _migration_001_global_memory_index(conn: sqlite3.Connection, engine) -> None:
    """Create the global memory_index table.

    If the old session-scoped table exists (with session_id column),
    migrate its data and replace with the new global schema.
    """
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_index'")
    old_table = cursor.fetchone()

    if old_table:
        col_cursor = conn.execute("PRAGMA table_info(memory_index)")
        columns = col_cursor.fetchall()
        has_session_id = any(c[1] == "session_id" for c in columns)  # column name at index 1

        if has_session_id:
            logger.info("Migrating old session-scoped memory_index to new global schema")
            try:
                rows = conn.execute(
                    "SELECT key, value, updated_at FROM memory_index ORDER BY updated_at DESC"
                ).fetchall()
            except Exception:
                rows = []

            conn.execute("DROP TABLE memory_index")

            conn.execute("""
                CREATE TABLE memory_index (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            seen = set()
            for row in rows:
                key = row[0]
                if key not in seen:
                    seen.add(key)
                    try:
                        conn.execute(
                            "INSERT INTO memory_index (key, value, updated_at) VALUES (?, ?, ?)",
                            (key, row[1], row[2] if len(row) > 2 else None),
                        )
                    except Exception:
                        pass
            logger.info("Migrated %d entries to global memory_index", len(seen))
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_index (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)


_MEMORY_MIGRATIONS = (
    _migration_001_global_memory_index,
)


async def init_memory_db() -> None:
    """Initialize memory.db: create tables and run pending migrations.

    Uses synchronous sqlite3 to avoid aiosqlite thread lifecycle issues.
    The connection is closed immediately after initialization.
    """
    db_path = resolve_memory_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        row = cursor.fetchone()
        current = 0
        if row:
            c2 = conn.execute("SELECT version FROM schema_version LIMIT 1")
            r = c2.fetchone()
            current = r["version"] if r else 0
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")

        # Simple sync engine wrapper
        class _SyncEngine:
            def execute(self, c, sql, params=()):
                return c.execute(sql, params)
            def commit(self, c):
                c.commit()

        engine = _SyncEngine()

        async def _run_migrations():
            nonlocal current
            for version, migration in enumerate(_MEMORY_MIGRATIONS[current:], start=current + 1):
                migration(conn, engine)
                conn.execute("DELETE FROM schema_version")
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                conn.commit()
                current = version

        import asyncio
        await _run_migrations()

        conn.commit()
        mark_initialized(db_path)
        logger.info("memory.db initialized at %s (migration v%s)", db_path, current)
    finally:
        conn.close()
