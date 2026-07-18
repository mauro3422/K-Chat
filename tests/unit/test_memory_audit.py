from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.memory_audit import _content_hash, resolve_audit_root, run_audit
from src.memory.maintenance.audit_cli import build_parser
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository


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
    conn.execute(
        """
        CREATE TABLE memory_processing_catalog (
            source TEXT NOT NULL,
            source_key TEXT NOT NULL,
            item_idx INTEGER NOT NULL,
            stage TEXT NOT NULL,
            content_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            processor TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            metadata TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (source, source_key, item_idx, stage)
        )
        """
    )
    MemoryWorkCatalogRepository.ensure_schema(conn)
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
    assert report["status"] == "attention"
    assert report["health"]["integrity"]["status"] == "ok"
    assert report["health"]["coverage"]["status"] == "attention"
    assert report["health"]["coverage"]["metrics"]["exchange_coverage_ratio"] == 0.0
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
    MemoryWorkCatalogRepository(str(memory_db)).mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash="stale-hash",
        status="embedded",
        vec_rowid=1,
        reason="test_fixture",
    )

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    assert report["summary"]["sessions_with_stale_vectors"] == 1
    assert report["sessions"][0]["stale_vectors"][0]["hash"] == "stale-hash"[:12]
    assert report["health"]["coverage"]["status"] == "attention"
    assert report["health"]["integrity"]["status"] == "ok"
    assert report["ok"] is True


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


def test_memory_audit_reports_processing_catalog_statuses(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    prompt = (
        "Session: Session One\n\n"
        "User: Tell me a meaningful thing about distributed memory systems.\n"
        "Assistant: Distributed memory systems need stable hashes for incremental work."
        "\n\nExtract new info or NO_NEW_INFO"
    )
    digest = _content_hash(prompt)
    exchange_text = (
        "User: Tell me a meaningful thing about distributed memory systems.\n"
        "Assistant: Distributed memory systems need stable hashes for incremental work."
    )
    exchange_digest = _content_hash(exchange_text)

    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (1, 'session', 's1', 0, ?, ?, ?, '2026-06-27T10:00:01')
        """,
        (
            exchange_text,
            exchange_digest,
            exchange_digest,
        ),
    )
    conn.execute(
        """
        INSERT INTO memory_processing_catalog (
            source, source_key, item_idx, stage, content_hash, status, processor, reason
        )
        VALUES ('session', 's1', -1, 'curated', ?, 'processed', 'curate_sessions', 'no_new_info')
        """,
        (digest,),
    )
    conn.commit()
    conn.close()
    MemoryWorkCatalogRepository(str(memory_db)).mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash=exchange_digest,
        status="embedded",
        vec_rowid=1,
        reason="test_fixture",
    )

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    processing = report["processing_catalog"]
    assert processing["exists"] is True
    assert processing["total"] == 1
    assert processing["by_stage_status"] == {"curated": {"processed": 1}}
    assert processing["stale"] == 0
    assert report["summary"]["processing_failed"] == 0
    assert report["summary"]["processing_stale"] == 0
    assert report["ok"] is True


def test_memory_audit_reports_stale_processing_catalog_row(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)

    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (1, 'session', 's1', 0, ?, ?, ?, '2026-06-27T10:00:01')
        """,
        (
            "User: Tell me a meaningful thing about distributed memory systems.\n"
            "Assistant: Distributed memory systems need stable hashes for incremental work.",
            "hash",
            "hash",
        ),
    )
    conn.execute(
        """
        INSERT INTO memory_processing_catalog (
            source, source_key, item_idx, stage, content_hash, status, processor, reason
        )
        VALUES ('session', 's1', -1, 'curated', 'old-hash', 'processed', 'curate_sessions', 'old')
        """
    )
    conn.commit()
    conn.close()

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    processing = report["processing_catalog"]
    assert processing["stale"] == 1
    assert processing["stale_rows"][0]["stage"] == "curated"
    assert report["summary"]["processing_stale"] == 1
    assert report["ok"] is False


def test_memory_audit_scores_curated_memory_quality(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)

    conn = sqlite3.connect(memory_db)
    conn.execute(
        "INSERT INTO memory_index (key, value, updated_at) VALUES (?, ?, ?)",
        ("test", "ok", "2026-06-29T10:00:00"),
    )
    conn.execute(
        "INSERT INTO memory_index (key, value, updated_at) VALUES (?, ?, ?)",
        (
            "user:workflow",
            "2026-06-29 10:00 | Mauro prefers catalog-first memory sync with explicit embedding pipeline identity.",
            "2026-06-29T10:01:00",
        ),
    )
    conn.commit()
    conn.close()

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    quality = report["curated_memory_quality"]
    assert quality["total"] == 2
    assert quality["low_signal"] == 1
    assert quality["probe"] == 1
    assert quality["avg_quality_score"] < 1.0
    assert report["summary"]["curated_low_signal"] == 1
    assert report["health"]["quality"]["status"] == "warning"
    assert report["health"]["quality"]["metrics"]["missing_timestamp"] == 1


def test_memory_audit_reports_quality_warning_without_blocking_integrity(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    exchange_text = (
        "User: Tell me a meaningful thing about distributed memory systems.\n"
        "Assistant: Distributed memory systems need stable hashes for incremental work."
    )
    digest = _content_hash(exchange_text)
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (1, 'session', 's1', 0, ?, ?, ?, '2026-07-17T10:00:00')
        """,
        (exchange_text, digest, digest),
    )
    conn.execute(
        "INSERT INTO memory_index (key, value, updated_at) VALUES ('test:probe', 'ok', '2026-07-17T10:00:00')"
    )
    conn.commit()
    conn.close()
    MemoryWorkCatalogRepository(str(memory_db)).mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash=digest,
        status="embedded",
        vec_rowid=1,
        reason="test_fixture",
    )
    artifact_dir = tmp_path / "memory" / "2026" / "07" / "17"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "daily.md").write_text("# Daily\n", encoding="utf-8")
    (artifact_dir / "transversal.md").write_text("# Transversal\n", encoding="utf-8")

    report = run_audit(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=str(tmp_path),
    )

    assert report["health"]["integrity"]["status"] == "ok"
    assert report["health"]["coverage"]["status"] == "ok"
    assert report["health"]["quality"]["status"] == "warning"
    assert report["status"] == "warning"
    assert report["ok"] is True


def test_memory_audit_does_not_flag_detailed_technical_history_as_probe_or_vague(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)

    value = (
        "2026-07-18 02:00 | Se completaron 28 tests focalizados y quedó pendiente "
        "una mejora opcional. La implementación conserva hashes, catálogo, vectores "
        "y trazabilidad entre ambos nodos sin inconsistencias."
    )
    conn = sqlite3.connect(memory_db)
    conn.execute(
        "INSERT INTO memory_index (key, value, updated_at) VALUES (?, ?, ?)",
        ("fix:memory-catalog", value, "2026-07-18T02:00:00"),
    )
    conn.commit()
    conn.close()

    quality = run_audit(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=str(tmp_path),
    )["curated_memory_quality"]

    assert quality["probe"] == 0
    assert quality["vague"] == 0
    assert quality["low_signal"] == 0


def test_memory_audit_accepts_short_specific_user_fact(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)

    conn = sqlite3.connect(memory_db)
    conn.execute(
        "INSERT INTO memory_index (key, value, updated_at) VALUES (?, ?, ?)",
        (
            "user:ubicacion",
            "2026-07-18 02:00 | Tucumán, Argentina (capital).",
            "2026-07-18T02:00:00",
        ),
    )
    conn.commit()
    conn.close()

    quality = run_audit(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=str(tmp_path),
    )["curated_memory_quality"]

    assert quality["low_signal"] == 0


def test_memory_audit_reports_uncataloged_memory_vectors(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    digest = _content_hash("2026-06-29 10:00 | Save memory embeddings must be cataloged.")

    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (4, 'memory', 'user:sync', 0, ?, ?, '', '2026-06-29T10:00:00')
        """,
        ("2026-06-29 10:00 | Save memory embeddings must be cataloged.", digest),
    )
    conn.commit()
    conn.close()

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    assert report["ok"] is False
    assert report["catalog"]["uncataloged_vectors"] == 1
    assert report["catalog"]["uncataloged_by_source"] == {"memory": 1}
    assert report["summary"]["uncataloged_vectors"] == 1


def test_memory_audit_fails_on_missing_catalog_vector_link(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    MemoryWorkCatalogRepository(str(memory_db)).mark(
        source="memory",
        source_key="lan_field_smoke:ghost",
        item_idx=0,
        content_hash="ghost-hash",
        status="embedded",
        vec_rowid=99,
        reason="test_fixture",
    )

    report = run_audit(sessions_db=str(sessions_db), memory_db=str(memory_db), root=str(tmp_path))

    assert report["ok"] is False
    assert report["catalog"]["missing_vec_links"] == 1
    assert report["summary"]["catalog_missing_vec_links"] == 1
    assert report["status"] == "error"
    assert report["health"]["integrity"]["status"] == "error"


def test_resolve_audit_root_accepts_repo_and_src_memory(tmp_path):
    src_memory = tmp_path / "src" / "memory"
    src_memory.mkdir(parents=True)

    assert resolve_audit_root(tmp_path) == tmp_path.resolve()
    assert resolve_audit_root(src_memory) == tmp_path.resolve()
    assert resolve_audit_root(tmp_path / "memory") == tmp_path.resolve()


def test_memory_audit_cli_defaults_to_repository_root():
    args = build_parser().parse_args([])

    assert Path(args.root).resolve() == resolve_audit_root(Path(__file__))
    assert not Path(args.root).as_posix().endswith("src/memory")


def test_memory_audit_finds_daily_and_transversal_synthesis_from_src_memory_root(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    src_memory = tmp_path / "src" / "memory"
    src_memory.mkdir(parents=True)
    artifact_dir = tmp_path / "memory" / "2026" / "07" / "17"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "daily.md").write_text("# Daily\n", encoding="utf-8")
    (artifact_dir / "transversal.md").write_text("# Transversal\n", encoding="utf-8")

    report = run_audit(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=str(src_memory),
    )

    assert Path(report["paths"]["root"]) == tmp_path.resolve()
    assert report["synthesis"]["exists"] is True
    assert report["synthesis"]["count"] == 1
    assert report["synthesis"]["daily"]["exists"] is True
    assert report["synthesis"]["transversal"]["exists"] is True
    assert report["health"]["coverage"]["metrics"]["daily_synthesis_count"] == 1
    assert report["health"]["coverage"]["metrics"]["transversal_synthesis_count"] == 1
