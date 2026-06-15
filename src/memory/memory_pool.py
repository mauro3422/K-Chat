"""Connection pool for memory.db (curated, syncable memory).

Separate from the sessions.db connection pool to keep the two databases
independent and allow syncing memory.db across devices.
"""

import os
import aiosqlite
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.lifecycle import is_initialized


_conn_storage: dict[str, Any] = {"conn": None, "db_path": None}


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
    """Get a cached connection to memory.db (singleton per process)."""
    db_path = resolve_memory_db_path()

    raw = _conn_storage["conn"]
    cached_path = _conn_storage["db_path"]

    if raw is not None and cached_path != db_path:
        await raw.close()
        raw = None
        _conn_storage["conn"] = None

    if raw is None:
        # Ensure DB is initialized BEFORE opening the pooled connection
        if not is_initialized(db_path):
            from src.memory.memory_schema import init_memory_db
            await init_memory_db()

        raw = await get_memory_raw_conn(db_path)
        _conn_storage["conn"] = raw
        _conn_storage["db_path"] = db_path

    return raw
