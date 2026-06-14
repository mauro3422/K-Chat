import aiosqlite
import os
from typing import Any


class SQLiteEngine:
    async def connect(self) -> aiosqlite.Connection:
        from src.memory.db_path import resolve_db_path

        db_path = resolve_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = await aiosqlite.connect(db_path)
        # We need to set the row factory if we want it to behave like the old one
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def execute(self, conn: aiosqlite.Connection, sql: str, params: tuple = ()) -> Any:
        return await conn.execute(sql, params)

    async def commit(self, conn: aiosqlite.Connection) -> None:
        await conn.commit()

    async def rollback(self, conn: aiosqlite.Connection) -> None:
        await conn.rollback()

    async def close(self, conn: aiosqlite.Connection) -> None:
        await conn.close()
