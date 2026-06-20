import logging
import os

from src.memory.conn_factory import configure_connection as _configure_connection, create_raw_conn as _get_raw_conn
from src.memory.db_path import resolve_db_path as _get_db_path
from src.memory.engine_state import get_engine
from src.memory.migration_runner import run_pending_migrations
from src.memory.lifecycle import mark_initialized as _mark_initialized
from src.memory.sqlite_engine import SQLiteEngine
from src.memory.migrations import MIGRATIONS

logger = logging.getLogger(__name__)


async def init_db() -> None:
    await init_db_for_path(_get_db_path())


async def init_db_for_path(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = await _get_raw_conn(db_path)
    engine = None
    try:
        await _configure_connection(conn)
        cursor = await conn.cursor()
        await cursor.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        try:
            await cursor.execute("SELECT MAX(version) AS version FROM schema_version")
            row = await cursor.fetchone()
            current = row["version"] if row else 0
        except Exception as e:
            logger.warning("Failed to read schema version, assuming 0: %s", e)
            current = 0

        engine = get_engine() or SQLiteEngine()
        await run_pending_migrations(conn, engine, MIGRATIONS, current)
        _mark_initialized(db_path)
    finally:
        if engine is not None:
            await engine.close(conn)
        else:
            await conn.close()
