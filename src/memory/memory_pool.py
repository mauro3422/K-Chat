"""Connection pool for memory.db (curated, syncable memory).

Separate from the sessions.db connection pool to keep the two databases
independent and allow syncing memory.db across devices.
"""

import os
import asyncio
import aiosqlite
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.lifecycle import is_initialized
from src.memory.connection_pool import ConnectionPool


_memory_pool = ConnectionPool(max_connections=5)


async def get_memory_raw_conn(db_path: str) -> aiosqlite.Connection:
    """Create a raw connection to the given memory.db path."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    raw_conn = await aiosqlite.connect(db_path)
    raw_conn.row_factory = aiosqlite.Row
    await raw_conn.execute("PRAGMA journal_mode=WAL")
    await raw_conn.execute("PRAGMA busy_timeout=5000")
    await raw_conn.execute("PRAGMA foreign_keys=ON")
    return raw_conn


async def get_memory_conn() -> aiosqlite.Connection:
    """Get a connection to memory.db from the per-process pool."""
    db_path = resolve_memory_db_path()

    raw = await _memory_pool.acquire(db_path)
    if raw is None:
        if not is_initialized(db_path):
            from src.memory.memory_schema import init_memory_db
            await init_memory_db()

        raw = await get_memory_raw_conn(db_path)

    return raw


async def return_memory_conn(conn: Any) -> None:
    """Return a memory.db connection to the pool."""
    db_path = resolve_memory_db_path()
    await _memory_pool.release(db_path, conn)


async def close_memory_all() -> None:
    """Close all connections in the memory pool."""
    await _memory_pool.close_all()
