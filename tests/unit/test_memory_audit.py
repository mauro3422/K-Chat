from __future__ import annotations

import sqlite3

from scripts.memory_audit import run_audit


def _init_sessions_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO sessions (session_id, name, created_at) VALUES ('s1', 'Session One', '2026-06-27T10:00:00')"
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES ('s1', 'user', ?, '2026-06-27T10:00:00')",
        ("Tell me a meaningful thing about distributed memory systems.",),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES ('s1', 'assistant', ?, '2026-06-27T10:00:01')",
        ("Distributed memory systems need stable hashes for incremental work.",),
    )
    conn.commit()
    conn.close()


def _init_memory_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE memory_index (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.execute(
        """
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT,
            exchange_idx INTEGER,
            text TEXT,
            hash TEXT,
            content_hash TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def test_memory_audit_reports_missing_session_vectors(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    assert report["summary"]["sessions_with_missing_vectors"] == 1
    assert report["summary"]["sessions_with_stale_vectors"] == 0
    assert report["sessions"][0]["missing_hashes"]
    assert report["ok"] is True


def test_memory_audit_reports_stale_session_vectors(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (1, 'session', 's1', 0, 'old text', 'stale-hash', 'stale-hash', '2026-06-27T09:00:00')
        """
    )
    conn.commit()
    conn.close()

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    assert report["summary"]["sessions_with_stale_vectors"] == 1
    assert report["sessions"][0]["stale_vectors"][0]["hash"] == "stale-hash"[:12]
    assert report["ok"] is False


def test_memory_audit_reports_legacy_vector_tables(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    conn = sqlite3.connect(sessions_db)
    conn.execute("CREATE TABLE vec_meta (rowid INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO vec_meta (rowid) VALUES (1)")
    conn.commit()
    conn.close()

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    assert report["legacy"]["sessions_db_has_vec_meta"] is True
    assert report["legacy"]["sessions_db_vec_meta_count"] == 1
