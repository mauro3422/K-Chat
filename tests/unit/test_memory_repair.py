from __future__ import annotations

import sqlite3

from scripts.memory_audit import _content_hash
from scripts.memory_repair import apply_catalog_repairs, plan_repairs, prune_stale_vectors


def _init_sessions_db(path, *, session_id="s1", user="Tell me about distributed memory catalogs.", assistant="They use content hashes to avoid duplicate work."):
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
        "INSERT INTO sessions (session_id, name, created_at) VALUES (?, 'Session One', '2026-06-27T10:00:00')",
        (session_id,),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, '2026-06-27T10:00:00')",
        (session_id, user),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'assistant', ?, '2026-06-27T10:00:01')",
        (session_id, assistant),
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


def _exchange_text(user="Tell me about distributed memory catalogs.", assistant="They use content hashes to avoid duplicate work."):
    return f"User: {user}\nAssistant: {assistant}"


def test_memory_repair_plans_and_applies_catalog_embedded(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    digest = _content_hash(_exchange_text())
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (1, 'session', 's1', 0, ?, ?, ?, '2026-06-27T10:00:02')
        """,
        (_exchange_text(), digest, digest),
    )
    conn.commit()
    conn.close()

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"catalog_embedded": 1}

    applied = apply_catalog_repairs(memory_db=str(memory_db), report=report)
    assert applied == 1
    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {}


def test_memory_repair_plans_dedup_from_other_session(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db, session_id="s2")
    _init_memory_db(memory_db)
    digest = _content_hash(_exchange_text())
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (7, 'session', 's1', 0, ?, ?, ?, '2026-06-27T10:00:02')
        """,
        (_exchange_text(), digest, digest),
    )
    conn.commit()
    conn.close()

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"catalog_deduped": 1}
    assert report.actions[0].vec_rowid == 7


def test_memory_repair_reports_stale_and_missing(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (8, 'session', 's1', 0, 'old text', 'old-hash', 'old-hash', '2026-06-27T09:00:00')
        """
    )
    conn.commit()
    conn.close()

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"stale_vector": 1, "missing_vector": 1}


def test_memory_repair_prunes_only_planned_stale_vectors(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    digest = _content_hash(_exchange_text())
    conn = sqlite3.connect(memory_db)
    conn.execute("CREATE TABLE vec_entries (rowid INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE vec_keywords (rowid INTEGER, word TEXT)")
    conn.execute("CREATE TABLE exchange_clusters (exchange_rowid INTEGER, cluster_id TEXT)")
    conn.execute("CREATE TABLE entity_mentions (exchange_rowid INTEGER, entity_id TEXT)")
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (8, 'session', 's1', 0, 'old text', 'old-hash', 'old-hash', '2026-06-27T09:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (9, 'session', 's1', 0, ?, ?, ?, '2026-06-27T10:00:02')
        """,
        (_exchange_text(), digest, digest),
    )
    for rowid in (8, 9):
        conn.execute("INSERT INTO vec_entries (rowid) VALUES (?)", (rowid,))
        conn.execute("INSERT INTO vec_keywords (rowid, word) VALUES (?, 'memory')", (rowid,))
        conn.execute("INSERT INTO exchange_clusters (exchange_rowid, cluster_id) VALUES (?, 'c1')", (rowid,))
        conn.execute("INSERT INTO entity_mentions (exchange_rowid, entity_id) VALUES (?, 'e1')", (rowid,))
    conn.commit()
    conn.close()

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"stale_vector": 1, "catalog_embedded": 1}

    assert prune_stale_vectors(memory_db=str(memory_db), report=report) == 1
    conn = sqlite3.connect(memory_db)
    try:
        assert conn.execute("SELECT rowid FROM vec_meta ORDER BY rowid").fetchall() == [(9,)]
        assert conn.execute("SELECT rowid FROM vec_entries ORDER BY rowid").fetchall() == [(9,)]
        assert conn.execute("SELECT rowid FROM vec_keywords ORDER BY rowid").fetchall() == [(9,)]
    finally:
        conn.close()
