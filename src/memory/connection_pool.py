import asyncio
import os
from contextvars import ContextVar
from typing import Any

from src.memory.db_path import resolve_db_path
from src.memory.conn_factory import create_raw_conn, configure_connection


class ConnectionPool:
    """Async-safe connection pool for SQLite databases."""

    def __init__(self, max_connections: int = 5):
        self._max = max_connections
        self._connections: dict[str, list[Any]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, db_path: str) -> Any | None:
        async with self._lock:
            pool = self._connections.get(db_path)
            if pool:
                return pool.pop()
            return None

    async def release(self, db_path: str, conn: Any) -> None:
        should_close = False
        async with self._lock:
            if db_path not in self._connections:
                self._connections[db_path] = []
            pool = self._connections[db_path]
            if len(pool) < self._max:
                pool.append(conn)
            else:
                should_close = True
        if should_close:
            await conn.close()

    async def close_all(self) -> None:
        async with self._lock:
            pools = list(self._connections.items())
            self._connections.clear()
        for db_path, pool in pools:
            for conn in pool:
                await conn.close()


_current_pool: ContextVar[ConnectionPool | None] = ContextVar(
    "kairos_connection_pool",
    default=None,
)


def get_pool() -> ConnectionPool:
    pool = _current_pool.get()
    if pool is None:
        pool = ConnectionPool()
        _current_pool.set(pool)
    return pool


def configure_connection_pool(pool: ConnectionPool | None) -> None:
    """Set the active connection pool explicitly, or clear it with None."""
    _current_pool.set(pool or ConnectionPool())


def reset_connection_pool() -> None:
    """Reset the active connection pool for the current context."""
    _current_pool.set(ConnectionPool())


class PooledConnection:
    """Wraps a connection so .close() returns it to the pool."""

    def __init__(self, conn: Any, db_path: str) -> None:
        self._conn = conn
        self._db_path = db_path

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    async def close(self) -> None:
        if self._conn is not None:
            conn, self._conn = self._conn, None
            await return_conn(self._db_path, conn)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                await self.rollback()
            except Exception:
                logger.warning("Failed to rollback pooled connection", exc_info=True)
        await self.close()


async def get_conn(db_path: str | None = None) -> PooledConnection:
    if db_path is None:
        db_path = resolve_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    raw = await get_pool().acquire(db_path)
    if raw is None:
        raw = await create_raw_conn(db_path)
    return PooledConnection(raw, db_path)


async def return_conn(db_path: str, conn: Any) -> None:
    if isinstance(conn, PooledConnection):
        if conn._conn is not None:
            raw, conn._conn = conn._conn, None
            await get_pool().release(db_path, raw)
        return
    await get_pool().release(db_path, conn)


async def close_all() -> None:
    await get_pool().close_all()
