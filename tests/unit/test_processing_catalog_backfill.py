from __future__ import annotations

import sqlite3

from scripts.backfill_processing_catalog import run_backfill
from scripts.memory_audit import _content_hash
from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository


def _init_sessions_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
    conn.execute(
        "INSERT INTO sessions (session_id, name, created_at) VALUES ('s1', 'Session One', '2026-06-27T10:00:00')"
    )
    conn.commit()
    conn.close()


def _init_memory_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT,
            exchange_idx INTEGER,
            text TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text)
        VALUES (1, 'session', 's1', 0, ?)
        """,
        ("User: hola\nAssistant: memoria distribuida necesita hashes estables y catalogos observables.",),
    )
    conn.commit()
    conn.close()


def test_processing_catalog_backfill_marks_observed_sessions_and_existing_synthesis(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    report = tmp_path / "memory" / "synthesis" / "2026" / "06" / "27.md"
    report.parent.mkdir(parents=True)
    report.write_text("# Daily Synthesis - 2026-06-27\n", encoding="utf-8")

    result = run_backfill(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=tmp_path,
        dry_run=False,
    )

    assert result["sessions_observed"] == 1
    assert result["stale_curated_sessions_refreshed"] == 0
    assert result["daily_synthesis_processed"] == 1

    conn = sqlite3.connect(memory_db)
    rows = conn.execute(
        "SELECT source, source_key, stage, status, processor, reason FROM memory_processing_catalog ORDER BY source, stage"
    ).fetchall()
    conn.close()

    assert rows == [
        ("daily_synthesis", "2026-06-27", "generated", "processed", "backfill_processing_catalog", "existing_report_seen"),
        ("session", "s1", "curation_candidate", "observed", "backfill_processing_catalog", "vectorized_session_seen"),
    ]


def test_processing_catalog_backfill_dry_run_does_not_write(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)

    result = run_backfill(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=tmp_path,
        dry_run=True,
    )

    assert result["sessions_observed"] == 1
    assert result["stale_curated_sessions_refreshed"] == 0

    conn = sqlite3.connect(memory_db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_processing_catalog'"
    ).fetchall()
    conn.close()

    assert rows == []


def test_processing_catalog_backfill_reopens_stale_curated_session(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    expected_prompt = (
        "Session: Session One\n\n"
        "User: hola\nAssistant: memoria distribuida necesita hashes estables y catalogos observables."
        "\n\nExtract new info or NO_NEW_INFO"
    )
    expected_hash = _content_hash(expected_prompt)
    catalog = MemoryProcessingCatalogRepository(str(memory_db))
    catalog.mark(
        source="session",
        source_key="s1",
        item_idx=-1,
        stage="curated",
        content_hash="old-hash",
        status="processed",
        processor="curate_sessions",
        reason="old",
    )

    result = run_backfill(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=tmp_path,
        dry_run=False,
    )

    assert result["stale_curated_sessions_refreshed"] == 1
    row = catalog.get(source="session", source_key="s1", item_idx=-1, stage="curated")
    assert row is not None
    assert row["content_hash"] == expected_hash
    assert row["status"] == "pending"
    assert row["processor"] == "backfill_processing_catalog"
    assert row["reason"] == "content_changed_reprocess_required"
