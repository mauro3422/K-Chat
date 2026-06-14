import logging
from contextlib import asynccontextmanager
from typing import Any

from src.memory.connection_pool import get_conn
from src.memory.engine_state import get_engine

logger = logging.getLogger(__name__)


class _BaseRepository:
    _table_name: str = ""

    def __init__(self, conn: Any = None, engine: Any = None) -> None:
        self._conn = conn
        self._engine = engine

    async def _get_conn(self) -> Any:
        if self._conn is not None:
            return self._conn
        return await get_conn()

    @asynccontextmanager
    async def _transaction(self):
        conn = await self._get_conn()
        engine = self._engine or get_engine()
        try:
            yield conn
            if engine is not None:
                await engine.commit(conn)
            else:
                await conn.commit()
        except Exception:
            if engine is not None:
                await engine.rollback(conn)
            else:
                await conn.rollback()
            logger.exception("Database transaction failed")
            raise

    async def delete_by_session(self, session_id: str, cursor: Any = None) -> None:
        if not self._table_name:
            raise NotImplementedError("Subclass must set _table_name")
        sql = f"DELETE FROM {self._table_name} WHERE session_id = ?"
        if cursor is not None:
            await cursor.execute(sql, (session_id,))
        else:
            async with self._transaction() as conn:
                await conn.execute(sql, (session_id,))


__all__ = ["_BaseRepository"]
