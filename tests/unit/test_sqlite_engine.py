"""Tests for sqlite_engine.py"""
import os
import sqlite3
from unittest.mock import patch

import pytest

from src.memory.sqlite_engine import SQLiteEngine


class TestSQLiteEngine:
    def test_connect_creates_db_file(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            assert os.path.exists(db_path)
            conn.close()

    def test_connect_sets_wal_mode(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            cur = conn.execute("PRAGMA journal_mode")
            assert cur.fetchone()[0].lower() == "wal"
            conn.close()

    def test_connect_sets_busy_timeout(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            cur = conn.execute("PRAGMA busy_timeout")
            assert cur.fetchone()[0] == 5000
            conn.close()

    def test_connect_sets_foreign_keys_on(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            cur = conn.execute("PRAGMA foreign_keys")
            assert cur.fetchone()[0] == 1
            conn.close()

    def test_execute_returns_cursor(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            cur = engine.execute(conn, "SELECT 1 AS val")
            assert cur.fetchone()[0] == 1
            conn.close()

    def test_execute_with_params(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            engine.execute(conn, "CREATE TABLE _test (x INTEGER)")
            engine.execute(conn, "INSERT INTO _test VALUES (?)", (42,))
            cur = engine.execute(conn, "SELECT x FROM _test")
            assert cur.fetchone()[0] == 42
            conn.close()

    def test_commit_and_rollback(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            engine.execute(conn, "CREATE TABLE IF NOT EXISTS _test_rollback (x INTEGER)")
            engine.execute(conn, "INSERT INTO _test_rollback VALUES (1)")
            engine.rollback(conn)
            cur = engine.execute(conn, "SELECT COUNT(*) FROM _test_rollback")
            assert cur.fetchone()[0] == 0
            conn.close()

    def test_commit_persists_data(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            engine.execute(conn, "CREATE TABLE IF NOT EXISTS _test_commit (x INTEGER)")
            engine.execute(conn, "INSERT INTO _test_commit VALUES (99)")
            engine.commit(conn)
            cur = engine.execute(conn, "SELECT COUNT(*) FROM _test_commit")
            assert cur.fetchone()[0] == 1
            conn.close()

    def test_close_makes_conn_unusable(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("src.memory.db_path.resolve_db_path", return_value=db_path):
            engine = SQLiteEngine()
            conn = engine.connect()
            engine.close(conn)
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")
