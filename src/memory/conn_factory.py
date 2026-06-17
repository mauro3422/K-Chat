"""Standalone connection factory — no circular deps with bootstrap/schema."""

import aiosqlite
from typing import Any

from src.memory.engine_state import get_engine


async def create_raw_conn(db_path: str) -> aiosqlite.Connection:
    """Create a raw aiosqlite connection with pragmas configured."""
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
    """Configure pragmas on an existing aiosqlite connection."""
    engine = get_engine()
    if engine is not None:
        await engine.execute(conn, "PRAGMA journal_mode=WAL")
        await engine.execute(conn, "PRAGMA busy_timeout=5000")
        await engine.execute(conn, "PRAGMA foreign_keys=ON")
    else:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
