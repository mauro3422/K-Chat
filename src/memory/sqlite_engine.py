import sqlite3
import os
from typing import Any


class SQLiteEngine:
    def connect(self) -> sqlite3.Connection:
        from src.memory.db_path import resolve_db_path

        db_path = resolve_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def execute(self, conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Any:
        return conn.execute(sql, params)

    def commit(self, conn: sqlite3.Connection) -> None:
        conn.commit()

    def rollback(self, conn: sqlite3.Connection) -> None:
        conn.rollback()

    def close(self, conn: sqlite3.Connection) -> None:
        conn.close()
