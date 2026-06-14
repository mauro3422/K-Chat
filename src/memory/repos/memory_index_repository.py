import logging

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class MemoryIndexRepository(_BaseRepository):
    _table_name = "memory_index"

    async def upsert(self, session_id: str, key: str, value: str) -> None:
        async with self._transaction() as conn:
            await conn.execute(
                """INSERT INTO memory_index (session_id, key, value)
                   VALUES (?, ?, ?)
                   ON CONFLICT(session_id, key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = CURRENT_TIMESTAMP""",
                (session_id, key, value),
            )

    async def get(self, session_id: str, key: str) -> str | None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT value FROM memory_index WHERE session_id = ? AND key = ?",
            (session_id, key),
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def get_all(self, session_id: str) -> list[dict[str, str]]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT key, value FROM memory_index WHERE session_id = ? ORDER BY key",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [{"key": row["key"], "value": row["value"]} for row in rows]

    async def delete(self, session_id: str, key: str) -> None:
        async with self._transaction() as conn:
            await conn.execute(
                "DELETE FROM memory_index WHERE session_id = ? AND key = ?",
                (session_id, key),
            )


__all__ = ["MemoryIndexRepository"]
