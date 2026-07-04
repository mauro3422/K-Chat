from __future__ import annotations

import sqlite3

from scripts.memory_audit import _content_hash
from scripts.memory_repair import apply_catalog_repairs, plan_repairs, prune_stale_vectors
from src.memory.maintenance.repair import RepairAction, _dedupe_actions
from src.memory.embedding_identity import memory_entry_embedding_identity, session_exchange_embedding_identity
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository


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
    catalog = MemoryWorkCatalogRepository(str(memory_db))
    assert catalog.is_processed(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash=digest,
        **session_exchange_embedding_identity().as_catalog_kwargs(),
    )
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


def test_memory_repair_dedupes_repeated_logical_actions():
    action = RepairAction(
        action="orphan_catalog_row",
        source="session",
        source_key="deleted-session",
        item_idx=0,
        content_hash="ghost-hash",
        status="embedded",
        vec_rowid=99,
        reason="session_and_vec_missing",
    )
    other = RepairAction(
        action="stale_vector",
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash="old-hash",
        vec_rowid=8,
        reason="current_hash=new",
    )

    assert _dedupe_actions([action, action, other]) == [action, other]


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


def test_memory_repair_detects_and_fixes_broken_catalog_link(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    digest = _content_hash(_exchange_text())
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (9, 'session', 's1', 0, ?, ?, ?, '2026-06-27T10:00:02')
        """,
        (_exchange_text(), digest, digest),
    )
    conn.commit()
    conn.close()
    catalog = MemoryWorkCatalogRepository(str(memory_db))
    catalog.mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash=digest,
        status="embedded",
        vec_rowid=8,
        reason="old_row",
        **session_exchange_embedding_identity().as_catalog_kwargs(),
    )

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"broken_catalog_link": 1, "catalog_embedded": 1}

    assert apply_catalog_repairs(memory_db=str(memory_db), report=report) == 1
    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {}


def test_memory_repair_backfills_memory_vector_catalog_rows(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    digest = _content_hash("2026-06-29 10:00 | Mauro prefers cataloged save_memory embeddings.")
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (11, 'memory', 'user:workflow', 0, ?, ?, '', '2026-06-29T10:00:02')
        """,
        ("2026-06-29 10:00 | Mauro prefers cataloged save_memory embeddings.", digest),
    )
    conn.commit()
    conn.close()

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"missing_vector": 1, "catalog_memory_embedded": 1}

    assert apply_catalog_repairs(memory_db=str(memory_db), report=report) == 1
    catalog = MemoryWorkCatalogRepository(str(memory_db))
    identity = memory_entry_embedding_identity().as_catalog_kwargs()
    row = catalog.get(source="memory", source_key="user:workflow", item_idx=0, **identity)
    assert row is not None
    assert row["status"] == "embedded"
    assert row["vec_rowid"] == 11
    assert row["content_hash"] == digest
    assert catalog.is_processed(
        source="memory",
        source_key="user:workflow",
        item_idx=0,
        content_hash=digest,
        **identity,
    )


def test_memory_repair_ignores_legacy_default_identity_catalog_row(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    digest = _content_hash(_exchange_text())
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (12, 'session', 's1', 0, ?, ?, ?, '2026-06-27T10:00:02')
        """,
        (_exchange_text(), digest, digest),
    )
    conn.commit()
    conn.close()

    catalog = MemoryWorkCatalogRepository(str(memory_db))
    catalog.mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash=digest,
        status="embedded",
        vec_rowid=12,
        reason="legacy_default_identity",
    )

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"catalog_embedded": 1}

    assert apply_catalog_repairs(memory_db=str(memory_db), report=report) == 1
    assert catalog.is_processed(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash=digest,
        **session_exchange_embedding_identity().as_catalog_kwargs(),
    )


def test_memory_repair_deletes_orphan_memory_catalog_row(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    catalog = MemoryWorkCatalogRepository(str(memory_db))
    catalog.mark(
        source="memory",
        source_key="lan_field_smoke:ghost",
        item_idx=0,
        content_hash="ghost-hash",
        status="embedded",
        vec_rowid=99,
        reason="test_fixture",
    )

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"missing_vector": 1, "orphan_catalog_row": 1}

    assert apply_catalog_repairs(memory_db=str(memory_db), report=report) == 1
    assert catalog.get(source="memory", source_key="lan_field_smoke:ghost", item_idx=0) is None


def test_memory_repair_deletes_orphan_session_catalog_row(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    catalog = MemoryWorkCatalogRepository(str(memory_db))
    catalog.mark(
        source="session",
        source_key="deleted-session",
        item_idx=0,
        content_hash="ghost-hash",
        status="embedded",
        vec_rowid=99,
        reason="test_fixture",
        **session_exchange_embedding_identity().as_catalog_kwargs(),
    )

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert report.counts == {"missing_vector": 1, "orphan_catalog_row": 1}

    assert apply_catalog_repairs(memory_db=str(memory_db), report=report) == 1
    assert catalog.get(
        source="session",
        source_key="deleted-session",
        item_idx=0,
        **session_exchange_embedding_identity().as_catalog_kwargs(),
    ) is None
