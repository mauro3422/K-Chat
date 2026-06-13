import logging
import os
from typing import Any

from src.memory.connection_pool import configure_connection as _configure_connection, get_raw_conn as _get_raw_conn
from src.memory.db_path import resolve_db_path as _get_db_path
from src.memory.engine_state import get_engine
from src.memory.lifecycle import mark_initialized as _mark_initialized
from src.memory.sqlite_engine import SQLiteEngine
from src.memory.migrations import MIGRATIONS

logger = logging.getLogger(__name__)


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
            current = row["version"] if row else 0
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
