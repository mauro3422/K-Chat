import logging
from contextlib import contextmanager
from typing import Any

from src.memory.connection_pool import get_conn
from src.memory.engine_state import get_engine

logger = logging.getLogger(__name__)


class _BaseRepository:
    _table_name: str = ""

    def __init__(self, conn: Any = None, engine: Any = None) -> None:
        self._conn = conn
        self._engine = engine

    def _get_conn(self) -> Any:
        if self._conn is not None:
            return self._conn
        return get_conn()

    @contextmanager
    def _transaction(self):
        conn = self._get_conn()
        engine = self._engine or get_engine()
        try:
            yield conn
            if engine is not None:
                engine.commit(conn)
            else:
                conn.commit()
        except Exception:
            if engine is not None:
                engine.rollback(conn)
            else:
                conn.rollback()
            logger.exception("Database transaction failed")
            raise

    def delete_by_session(self, session_id: str, cursor: Any = None) -> None:
        if not self._table_name:
            raise NotImplementedError("Subclass must set _table_name")
        sql = f"DELETE FROM {self._table_name} WHERE session_id = ?"
        if cursor is not None:
            cursor.execute(sql, (session_id,))
        else:
            with self._transaction() as conn:
                conn.cursor().execute(sql, (session_id,))


__all__ = ["_BaseRepository"]
