"""Schema and initialization for deleted_sessions.db.

This database stores snapshots of deleted sessions so that semantic
search can still find "ghost" memories — even after the session is gone.
"""

from __future__ import annotations
import logging
import os
import sqlite3

from src.memory.memory_db_path import resolve_memory_db_path

logger = logging.getLogger(__name__)

DELETED_DB_DIR = "data"
DELETED_DB_NAME = "deleted_sessions.db"

# ── Path resolution ────────────────────────────────────────────────────────

def resolve_deleted_db_path() -> str:
    """Return the path to deleted_sessions.db.

    Priority:
    1. DELETED_SESSIONS_DB_PATH env var
    2. <project_root>/data/deleted_sessions.db
    """
    env_path = os.environ.get("DELETED_SESSIONS_DB_PATH")
    if env_path:
        return env_path

    # Default: next to memory.db
    memory_db_path = resolve_memory_db_path()
    base_dir = os.path.dirname(memory_db_path)
    return os.path.join(base_dir, DELETED_DB_NAME)


# ── Schema version tracking (sync engine) ──────────────────────────────────

class _SyncEngine:
    """Minimal sync engine wrapper for legacy migration runner compatibility."""
    def execute(self, c, sql, params=()):
        return c.execute(sql, params)
    def commit(self, c):
        c.commit()


# ── Migrations ─────────────────────────────────────────────────────────────

def _migration_001_deleted_sessions_table(conn: sqlite3.Connection, engine) -> None:
    """Create the deleted_sessions table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deleted_sessions (
            session_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            message_count INTEGER NOT NULL DEFAULT 0,
            summary TEXT NOT NULL DEFAULT '',
            topics TEXT NOT NULL DEFAULT '[]',
            deleted_at TEXT NOT NULL DEFAULT ''
        )
    """)
    logger.info("deleted_sessions table created")


def _migration_002_vec_store(conn: sqlite3.Connection, engine) -> None:
    """Create vector store tables for semantic search on deleted sessions."""
    try:
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
    except Exception as e:
        logger.warning("sqlite-vec not available, vector store disabled: %s", e)
        return

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
            embedding float[384] distance_metric=cosine
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT NOT NULL DEFAULT 'deleted_session',
            source_key TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_del_vec_source ON vec_meta (source, source_key)""")
    logger.info("Deleted sessions vector store tables created")


_DELETED_SESSION_MIGRATIONS = (
    _migration_001_deleted_sessions_table,
    _migration_002_vec_store,
)


# ── Init function ──────────────────────────────────────────────────────────

def init_deleted_sessions_db() -> str:
    """Initialize deleted_sessions.db and run pending migrations.

    Uses synchronous sqlite3 (same pattern as memory_schema.py).

    Returns:
        The path to the initialized database.
    """
    db_path = resolve_deleted_db_path()
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

        engine = _SyncEngine()
        for version, migration in enumerate(
            _DELETED_SESSION_MIGRATIONS[current:], start=current + 1
        ):
            migration(conn, engine)
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (version,),
            )
            conn.commit()
            current = version

        conn.commit()
        logger.info(
            "deleted_sessions.db initialized at %s (migration v%s)", db_path, current
        )
    except Exception:
        logger.exception("Failed to initialize deleted_sessions.db at %s", db_path)
        raise
    finally:
        conn.close()

    return db_path


__all__ = [
    "init_deleted_sessions_db",
    "resolve_deleted_db_path",
]
