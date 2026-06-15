"""GlobalMemoryIndexRepository — key-value memory storage in memory.db.

Unlike the old session-scoped MemoryIndexRepository, this stores memory
globally (no session_id). This is the structured counterpart of MEMORY.md
and gets synced across devices.

Creates a fresh aiosqlite connection per operation to avoid thread lifecycle
issues with aiosqlite's background worker threads.
"""

import logging
import os
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path

logger = logging.getLogger(__name__)


class GlobalMemoryIndexRepository:
    """Global memory index — key-value pairs shared across all sessions and devices.

    This is the programmatic counterpart of MEMORY.md. Every save_memory()
    call writes to BOTH MEMORY.md (text) AND this repository (structured).

    Does NOT use _BaseRepository to avoid coupling to sessions.db connection
    pool and aiosqlite thread lifecycle issues. Creates fresh connections.
    """

    _table_name = "memory_index"

    def __init__(self, conn: Any = None) -> None:
        self._conn = conn

    async def _get_conn(self) -> Any:
        """Return the injected connection or create a fresh one."""
        if self._conn is not None:
            return self._conn
        return await self._create_conn()

    async def _create_conn(self) -> Any:
        """Create a fresh aiosqlite connection to memory.db."""
        import aiosqlite
        db_path = resolve_memory_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def _ensure_table(self, conn: Any) -> None:
        """Ensure the memory_index table exists (lazy init)."""
        try:
            import sqlite3
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_index'"
            )
            row = await cur.fetchone()
            if not row:
                # Table doesn't exist — run sync init
                from src.memory.memory_schema import init_memory_db
                await init_memory_db()
        except Exception:
            from src.memory.memory_schema import init_memory_db
            await init_memory_db()

    async def upsert(self, key: str, value: str) -> None:
        """Insert or update a memory entry. Global scope — no session_id."""
        conn = await self._get_conn()
        try:
            await conn.execute(
                """INSERT INTO memory_index (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = CURRENT_TIMESTAMP""",
                (key, value),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    async def get(self, key: str) -> str | None:
        """Get a single memory entry by key."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT value FROM memory_index WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def get_all(self) -> list[dict[str, str]]:
        """Get all memory entries, ordered by key."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT key, value, updated_at FROM memory_index ORDER BY key",
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def search(self, query: str) -> list[dict[str, str]]:
        """Search memory entries by key or value (LIKE match)."""
        conn = await self._get_conn()
        pattern = f"%{query}%"
        cursor = await conn.execute(
            "SELECT key, value, updated_at FROM memory_index WHERE key LIKE ? OR value LIKE ? ORDER BY key",
            (pattern, pattern),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete(self, key: str) -> None:
        """Delete a memory entry by key."""
        conn = await self._get_conn()
        try:
            await conn.execute("DELETE FROM memory_index WHERE key = ?", (key,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    async def count(self) -> int:
        """Return the total number of memory entries."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM memory_index")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


__all__ = ["GlobalMemoryIndexRepository"]
