from unittest.mock import AsyncMock
"""Tests for sqlite_engine.py"""
import os
import aiosqlite
from unittest.mock import patch

import pytest

from src.memory.sqlite_engine import SQLiteEngine


class TestSQLiteEngine:
    @pytest.mark.anyio
    async def test_connect_creates_db_file(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            assert os.path.exists(db_path)
            await conn.close()

    @pytest.mark.anyio
    async def test_connect_sets_wal_mode(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            cur = await conn.execute("PRAGMA journal_mode")
            row = await cur.fetchone()
            assert row[0].lower() == "wal"
            await conn.close()

    @pytest.mark.anyio
    async def test_connect_sets_busy_timeout(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            cur = await conn.execute("PRAGMA busy_timeout")
            row = await cur.fetchone()
            assert row[0] == 5000
            await conn.close()

    @pytest.mark.anyio
    async def test_connect_sets_foreign_keys_on(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            cur = await conn.execute("PRAGMA foreign_keys")
            row = await cur.fetchone()
            assert row[0] == 1
            await conn.close()

    @pytest.mark.anyio
    async def test_execute_returns_cursor(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            cur = await engine.execute(conn, "SELECT 1 AS val")
            row = await cur.fetchone()
            assert row[0] == 1
            await conn.close()

    @pytest.mark.anyio
    async def test_execute_with_params(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            await engine.execute(conn, "CREATE TABLE _test (x INTEGER)")
            await engine.execute(conn, "INSERT INTO _test VALUES (?)", (42,))
            cur = await engine.execute(conn, "SELECT x FROM _test")
            row = await cur.fetchone()
            assert row[0] == 42
            await conn.close()

    @pytest.mark.anyio
    async def test_commit_and_rollback(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            await engine.execute(conn, "CREATE TABLE IF NOT EXISTS _test_rollback (x INTEGER)")
            await engine.execute(conn, "INSERT INTO _test_rollback VALUES (1)")
            await engine.rollback(conn)
            cur = await engine.execute(conn, "SELECT COUNT(*) FROM _test_rollback")
            row = await cur.fetchone()
            assert row[0] == 0
            await conn.close()

    @pytest.mark.anyio
    async def test_commit_persists_data(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            await engine.execute(conn, "CREATE TABLE IF NOT EXISTS _test_commit (x INTEGER)")
            await engine.execute(conn, "INSERT INTO _test_commit VALUES (99)")
            await engine.commit(conn)
            cur = await engine.execute(conn, "SELECT COUNT(*) FROM _test_commit")
            row = await cur.fetchone()
            assert row[0] == 1
            await conn.close()

    @pytest.mark.anyio
    async def test_close_makes_conn_unusable(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = await engine.connect()
            await engine.close(conn)
            with pytest.raises(ValueError):
                await conn.execute("SELECT 1")
