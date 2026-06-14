import os
import aiosqlite
from typing import Any

from src.memory.db_path import resolve_db_path
from src.memory.engine_state import get_engine

_conn_storage = {"conn": None, "db_path": None}


async def get_raw_conn(db_path: str):
    engine = get_engine()
    if engine is not None:
        return await engine.connect()
    raw_conn = await aiosqlite.connect(db_path)
    raw_conn.row_factory = aiosqlite.Row
    await raw_conn.execute("PRAGMA journal_mode=WAL")
    await raw_conn.execute("PRAGMA busy_timeout=5000")
    await raw_conn.execute("PRAGMA foreign_keys=ON")
    return raw_conn


async def configure_connection(conn: Any) -> None:
    engine = get_engine()
    if engine is not None:
        await engine.execute(conn, "PRAGMA journal_mode=WAL")
        await engine.execute(conn, "PRAGMA busy_timeout=5000")
        await engine.execute(conn, "PRAGMA foreign_keys=ON")
    else:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")


class PooledConnection:
    """Wraps a connection so .close() is a no-op (connection stays in the pool)."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    async def close(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


async def get_conn() -> PooledConnection:
    db_path = resolve_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    raw = _conn_storage["conn"]
    cached_path = _conn_storage["db_path"]
    
    if raw is not None and cached_path != db_path:
        await raw.close()
        raw = None
        _conn_storage["conn"] = None
        
    if raw is None:
        raw = await get_raw_conn(db_path)
        _conn_storage["conn"] = raw
        _conn_storage["db_path"] = db_path
        # Lazy import to avoid circular dependency
        from src.memory.bootstrap import ensure_db_initialized
        await ensure_db_initialized(db_path)
    return PooledConnection(raw)
