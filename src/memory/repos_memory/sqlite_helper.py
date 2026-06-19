"""Shared sqlite helpers for memory repositories."""

from __future__ import annotations

import os
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path


async def create_memory_db_connection() -> Any:
    import aiosqlite

    db_path = resolve_memory_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=5000")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn
