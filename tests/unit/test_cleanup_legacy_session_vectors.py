from __future__ import annotations

import sqlite3

from scripts.cleanup_legacy_session_vectors import apply_cleanup, inspect_legacy_tables


def _init_sessions_db(path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, content TEXT)")
        conn.execute("CREATE TABLE memory_index (session_id TEXT, key TEXT, value TEXT)")
        conn.execute("CREATE TABLE vec_meta (rowid INTEGER PRIMARY KEY, source TEXT)")
        conn.execute("CREATE TABLE vec_entries (rowid INTEGER PRIMARY KEY, embedding BLOB)")
        conn.execute("CREATE TABLE vec_keywords (rowid INTEGER, word TEXT)")
        conn.execute("CREATE TABLE topic_clusters (cluster_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE entities (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO sessions (session_id) VALUES ('s1')")
        conn.execute("INSERT INTO messages (session_id, content) VALUES ('s1', 'hello')")
        conn.execute("INSERT INTO memory_index (session_id, key, value) VALUES ('s1', 'k', 'v')")
        conn.execute("INSERT INTO vec_meta (rowid, source) VALUES (1, 'session')")
        conn.execute("INSERT INTO vec_keywords (rowid, word) VALUES (1, 'hello')")
        conn.commit()
    finally:
        conn.close()


def test_cleanup_legacy_session_vectors_dry_run_reports_legacy_tables(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    _init_sessions_db(sessions_db)

    report = inspect_legacy_tables(str(sessions_db))

    names = {table.name for table in report.planned_tables}
    assert {"vec_meta", "vec_entries", "vec_keywords", "topic_clusters", "entities"} <= names
    assert "sessions" not in names
    assert "messages" not in names
    assert "memory_index" not in names


def test_cleanup_legacy_session_vectors_apply_backs_up_and_preserves_session_tables(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    backup_root = tmp_path / "backups"
    _init_sessions_db(sessions_db)

    report = apply_cleanup(str(sessions_db), str(backup_root))

    assert report.backup_path
    assert (backup_root / "legacy-session-vectors").exists()
    assert set(report.dropped_tables or []) >= {"vec_meta", "vec_entries", "vec_keywords"}

    conn = sqlite3.connect(sessions_db)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"sessions", "messages", "memory_index"} <= tables
        assert "vec_meta" not in tables
        assert "vec_entries" not in tables
        assert "vec_keywords" not in tables
        assert conn.execute("SELECT COUNT(1) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(1) FROM messages").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(1) FROM memory_index").fetchone()[0] == 1
    finally:
        conn.close()

    backup = sqlite3.connect(report.backup_path)
    try:
        assert backup.execute("SELECT COUNT(1) FROM vec_meta").fetchone()[0] == 1
    finally:
        backup.close()
