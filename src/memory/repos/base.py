import logging
from contextlib import contextmanager
from typing import Any

from src.memory.database import get_conn, get_engine

logger = logging.getLogger(__name__)


class _BaseRepository:
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


__all__ = ["_BaseRepository"]
