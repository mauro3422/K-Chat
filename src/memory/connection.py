import logging
import os
import sqlite3
import threading
from typing import Any, Protocol

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


def set_engine(engine: DatabaseEngine | None) -> None:
    global _engine
    _engine = engine


def _get_raw_conn(db_path: str):
    if _engine is not None:
        return _engine.connect()
    raw_conn = sqlite3.connect(db_path, check_same_thread=False)
    raw_conn.execute("PRAGMA journal_mode=WAL")
    raw_conn.execute("PRAGMA busy_timeout=5000")
    return raw_conn


def _configure_connection(conn: Any) -> None:
    if _engine is not None:
        _engine.execute(conn, "PRAGMA journal_mode=WAL")
        _engine.execute(conn, "PRAGMA busy_timeout=5000")
        _engine.execute(conn, "PRAGMA foreign_keys=ON")
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
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    cached_path = getattr(_thread_local, "db_path", None)
    raw = getattr(_thread_local, "conn", None)
    if raw is not None and cached_path != db_path:
        raw.close()
        raw = None
        _thread_local.conn = None
    if raw is None:
        raw = _get_raw_conn(db_path)
        _thread_local.conn = raw
        _thread_local.db_path = db_path
        from src.memory.schema import _ensure_initialized
        _ensure_initialized(db_path)
    return PooledConnection(raw)
