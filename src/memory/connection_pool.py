import os
import sqlite3
import threading
from typing import Any

from src.memory.db_path import resolve_db_path
from src.memory.engine_state import get_engine
from src.memory.lifecycle import ensure_initialized as _ensure_initialized
from src.memory.bootstrap import ensure_db_initialized

_thread_local = threading.local()


def get_raw_conn(db_path: str):
    engine = get_engine()
    if engine is not None:
        return engine.connect()
    raw_conn = sqlite3.connect(db_path, check_same_thread=False)
    raw_conn.row_factory = sqlite3.Row
    raw_conn.execute("PRAGMA journal_mode=WAL")
    raw_conn.execute("PRAGMA busy_timeout=5000")
    raw_conn.execute("PRAGMA foreign_keys=ON")
    return raw_conn


def configure_connection(conn: Any) -> None:
    engine = get_engine()
    if engine is not None:
        engine.execute(conn, "PRAGMA journal_mode=WAL")
        engine.execute(conn, "PRAGMA busy_timeout=5000")
        engine.execute(conn, "PRAGMA foreign_keys=ON")
    else:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")


class PooledConnection:
    """Wraps a connection so .close() is a no-op (connection stays in the pool)."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def close(self) -> None:
        pass


def get_conn() -> PooledConnection:
    db_path = resolve_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    cached_path = getattr(_thread_local, "db_path", None)
    raw = getattr(_thread_local, "conn", None)
    if raw is not None and cached_path != db_path:
        raw.close()
        raw = None
        _thread_local.conn = None
    if raw is None:
        raw = get_raw_conn(db_path)
        _thread_local.conn = raw
        _thread_local.db_path = db_path
        ensure_db_initialized(db_path)
    return PooledConnection(raw)
