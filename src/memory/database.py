import sqlite3
import logging
import os
import threading
from typing import Any, Protocol

from src.memory.sqlite_engine import SQLiteEngine

logger = logging.getLogger(__name__)


class DatabaseEngine(Protocol):
    def connect(self) -> Any: ...
    def execute(self, conn: Any, sql: str, params: tuple = ()) -> Any: ...
    def commit(self, conn: Any) -> None: ...
    def rollback(self, conn: Any) -> None: ...
    def close(self, conn: Any) -> None: ...


def _get_db_path() -> str:
    from config import MEMORY_DB_PATH as _MEMORY_DB_PATH_CFG
    return os.environ.get("MEMORY_DB_PATH", _MEMORY_DB_PATH_CFG)

_thread_local = threading.local()

_engine: DatabaseEngine | None = None


def get_engine() -> DatabaseEngine | None:
    return _engine


def set_engine(engine: DatabaseEngine) -> None:
    global _engine
    _engine = engine


class PooledConnection:
    """Wraps a connection so .close() is a no-op (connection stays in the pool)."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def close(self) -> None:
        pass


def get_conn() -> PooledConnection:
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    cached_path = getattr(_thread_local, 'db_path', None)
    raw = getattr(_thread_local, 'conn', None)
    # If the DB path changed (e.g. test temp file), close old and reconnect
    if raw is not None and cached_path != db_path:
        raw.close()
        raw = None
        _thread_local.conn = None
    if raw is None:
        if _engine is not None:
            raw = _engine.connect()
        else:
            raw = sqlite3.connect(db_path, check_same_thread=False)
            raw.execute("PRAGMA journal_mode=WAL")
            raw.execute("PRAGMA busy_timeout=5000")
        _thread_local.conn = raw
        _thread_local.db_path = db_path
        init_db()
    return PooledConnection(raw)


def init_db() -> None:
    from src.memory.migrations import MIGRATIONS
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if _engine is not None:
        conn = _engine.connect()
    else:
        conn = sqlite3.connect(db_path)
    try:
        if _engine is not None:
            _engine.execute(conn, "PRAGMA journal_mode=WAL")
            _engine.execute(conn, "PRAGMA busy_timeout=5000")
            _engine.execute(conn, "PRAGMA foreign_keys=ON")
        else:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()
        # Ensure schema_version table has proper single-row tracking
        cursor.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        try:
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current = row[0] if row else 0
        except Exception:
            logger.exception("Failed to read schema version")
            current = 0

        effective_engine = _engine if _engine is not None else SQLiteEngine()
        for i, migration in enumerate(MIGRATIONS[current:], start=current + 1):
            migration(conn, effective_engine)
            cursor.execute("DELETE FROM schema_version")
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
            if _engine is not None:
                _engine.commit(conn)
            else:
                conn.commit()
    finally:
        if _engine is not None:
            _engine.close(conn)
        else:
            conn.close()
