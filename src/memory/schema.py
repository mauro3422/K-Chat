import logging
import os
import threading
from typing import Any

from src.memory.connection import _configure_connection, _get_raw_conn, _get_db_path, get_engine
from src.memory.sqlite_engine import SQLiteEngine
from src.memory.migrations import MIGRATIONS

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized_db_paths: set[str] = set()


def _mark_initialized(db_path: str) -> None:
    with _init_lock:
        _initialized_db_paths.add(db_path)


def _is_initialized(db_path: str) -> bool:
    with _init_lock:
        return db_path in _initialized_db_paths


def _ensure_initialized(db_path: str) -> None:
    if _is_initialized(db_path):
        return
    init_db_for_path(db_path)


def init_db() -> None:
    init_db_for_path(_get_db_path())


def init_db_for_path(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _get_raw_conn(db_path)
    try:
        _configure_connection(conn)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        try:
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current = row[0] if row else 0
        except Exception:
            logger.exception("Failed to read schema version")
            current = 0

        engine = get_engine() or SQLiteEngine()
        for i, migration in enumerate(MIGRATIONS[current:], start=current + 1):
            migration(conn, engine)
            cursor.execute("DELETE FROM schema_version")
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
            if get_engine() is not None:
                get_engine().commit(conn)
            else:
                conn.commit()
        _mark_initialized(db_path)
    finally:
        engine = get_engine()
        if engine is not None:
            engine.close(conn)
        else:
            conn.close()

