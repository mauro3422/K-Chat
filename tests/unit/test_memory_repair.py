from __future__ import annotations

import json
import sqlite3

import pytest

from scripts.memory_audit import _content_hash
from scripts.memory_repair import apply_catalog_repairs, plan_repairs, prune_stale_vectors
from src.memory.maintenance import repair_cli
from src.memory.maintenance.repair import RepairAction, RepairReport, _dedupe_actions, vectorize_missing
from src.memory.maintenance.repair_cli import build_parser, main
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


def _insert_session(
    path,
    *,
    session_id,
    user="Explain a second distributed memory catalog in detail.",
    assistant="The second catalog also uses stable content hashes and explicit identities.",
):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO sessions (session_id, name, created_at) VALUES (?, ?, '2026-06-27T11:00:00')",
        (session_id, f"Session {session_id}"),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, '2026-06-27T11:00:00')",
        (session_id, user),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'assistant', ?, '2026-06-27T11:00:01')",
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


def test_memory_repair_does_not_dedup_from_orphan_session(tmp_path):
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
    assert report.counts == {"missing_vector": 1, "stale_vector": 1}
    assert next(action for action in report.actions if action.action == "stale_vector").vec_rowid == 7


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


def test_memory_repair_scoped_plan_reports_only_requested_sessions(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _insert_session(sessions_db, session_id="s2")
    _init_memory_db(memory_db)

    report = plan_repairs(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        session_ids=["s2", "missing", "s2"],
    )

    assert report.scope_session_ids == ["s2", "missing"]
    assert report.missing_session_ids == ["missing"]
    assert report.counts == {"missing_vector": 1}
    assert {action.source_key for action in report.actions} == {"s2"}


def test_memory_repair_apply_defensively_limits_unscoped_report_and_is_idempotent(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    second_user = "Explain a second distributed memory catalog in detail."
    second_assistant = "The second catalog also uses stable content hashes and explicit identities."
    _insert_session(
        sessions_db,
        session_id="s2",
        user=second_user,
        assistant=second_assistant,
    )
    _init_memory_db(memory_db)
    first_text = _exchange_text()
    second_text = _exchange_text(second_user, second_assistant)
    conn = sqlite3.connect(memory_db)
    for rowid, session_id, text in ((1, "s1", first_text), (2, "s2", second_text)):
        digest = _content_hash(text)
        conn.execute(
            """
            INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
            VALUES (?, 'session', ?, 0, ?, ?, ?, '2026-06-27T11:00:02')
            """,
            (rowid, session_id, text, digest, digest),
        )
    conn.commit()
    conn.close()

    broad_report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))
    assert broad_report.counts == {"catalog_embedded": 2}
    assert apply_catalog_repairs(
        memory_db=str(memory_db),
        report=broad_report,
        session_ids=["s1"],
    ) == 1

    identity = session_exchange_embedding_identity().as_catalog_kwargs()
    catalog = MemoryWorkCatalogRepository(str(memory_db))
    assert catalog.get(source="session", source_key="s1", item_idx=0, **identity) is not None
    assert catalog.get(source="session", source_key="s2", item_idx=0, **identity) is None

    scoped_report = plan_repairs(
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        session_ids=["s1"],
    )
    assert scoped_report.counts == {}
    assert apply_catalog_repairs(memory_db=str(memory_db), report=scoped_report) == 0


@pytest.mark.asyncio
async def test_vectorize_missing_enforces_report_scope_and_stamps_source_node(monkeypatch):
    calls = []

    async def fake_vectorize_session(session_id, **kwargs):
        calls.append((session_id, kwargs))
        return len(kwargs["exchange_indexes"]), 0, [], []

    monkeypatch.setattr(
        "src.memory.vectorize_sessions.vectorize_session",
        fake_vectorize_session,
    )
    report = RepairReport(
        actions=[
            RepairAction("missing_vector", "session", "s1", 0, "hash-1"),
            RepairAction("missing_vector", "session", "s2", 0, "hash-2"),
        ],
        scope_session_ids=["s1"],
    )
    repos = object()

    result = await vectorize_missing(
        report,
        source_node_id=" primary-node ",
        repos=repos,
    )

    assert result == {"s1": 1}
    assert len(calls) == 1
    assert calls[0][0] == "s1"
    assert calls[0][1] == {
        "repos": repos,
        "exchange_indexes": {0},
        "source_node_id": "primary-node",
    }


@pytest.mark.asyncio
async def test_vectorize_missing_rejects_empty_source_node():
    report = RepairReport(
        actions=[RepairAction("missing_vector", "session", "s1", 0, "hash-1")],
        scope_session_ids=["s1"],
    )

    with pytest.raises(ValueError, match="source_node_id"):
        await vectorize_missing(report, source_node_id=" ", repos=object())


def test_memory_repair_cli_accepts_repeated_session_ids():
    args = build_parser().parse_args([
        "--session-id",
        "s1",
        "--session-id",
        "s2",
    ])

    assert args.session_id == ["s1", "s2"]


def test_memory_repair_cli_requires_source_node_for_vectorization():
    with pytest.raises(SystemExit) as exc:
        main(["--apply", "--vectorize-missing"])

    assert exc.value.code == 2


def test_memory_repair_cli_scoped_json_summary(tmp_path, capsys):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _insert_session(sessions_db, session_id="s2")
    _init_memory_db(memory_db)

    exit_code = main([
        "--sessions-db",
        str(sessions_db),
        "--memory-db",
        str(memory_db),
        "--session-id",
        "s1",
        "--json",
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == {
        "session_ids": ["s1"],
        "missing_session_ids": [],
    }
    assert payload["counts"] == {"missing_vector": 1}
    assert payload["batch_summary"]["planned"] == {"missing_vector": 1}
    assert payload["batch_summary"]["remaining"] == {"missing_vector": 1}
    assert list(payload["batch_summary"]["sessions"]) == ["s1"]


def test_memory_repair_cli_apply_passes_scope_and_emits_session_results(monkeypatch, capsys):
    reports = iter([
        RepairReport(
            actions=[
                RepairAction("catalog_noise", "session", "s1", 0, "noise-hash", status="noise"),
                RepairAction("missing_vector", "session", "s1", 1, "vector-hash"),
            ],
            scope_session_ids=["s1"],
        ),
        RepairReport(
            actions=[RepairAction("missing_vector", "session", "s1", 1, "vector-hash")],
            scope_session_ids=["s1"],
        ),
        RepairReport(scope_session_ids=["s1"]),
    ])
    calls = []

    def fake_plan_repairs(**kwargs):
        calls.append(("plan", kwargs))
        return next(reports)

    def fake_apply_catalog_repairs(**kwargs):
        calls.append(("apply", kwargs))
        return 1

    async def fake_vectorize_missing(report, **kwargs):
        calls.append(("vectorize", {"report": report, **kwargs}))
        return {"s1": 1}

    monkeypatch.setattr(repair_cli, "plan_repairs", fake_plan_repairs)
    monkeypatch.setattr(repair_cli, "apply_catalog_repairs", fake_apply_catalog_repairs)
    monkeypatch.setattr(repair_cli, "vectorize_missing", fake_vectorize_missing)

    exit_code = main([
        "--sessions-db",
        "sessions.db",
        "--memory-db",
        "memory.db",
        "--session-id",
        "s1",
        "--source-node-id",
        "primary-node",
        "--apply",
        "--vectorize-missing",
        "--json",
    ])

    assert exit_code == 0
    assert [call[0] for call in calls] == ["plan", "apply", "plan", "vectorize", "plan"]
    for name, kwargs in calls:
        if name == "plan":
            assert kwargs["session_ids"] == ["s1"]
        elif name == "apply":
            assert kwargs["session_ids"] == ["s1"]
        elif name == "vectorize":
            assert kwargs["session_ids"] == ["s1"]
            assert kwargs["source_node_id"] == "primary-node"

    summary = json.loads(capsys.readouterr().out)["batch_summary"]
    assert summary["applied_catalog_rows"] == 1
    assert summary["vectorized"] == 1
    assert summary["remaining"] == {}
    assert summary["sessions"]["s1"] == {
        "planned": {"catalog_noise": 1, "missing_vector": 1},
        "applied_catalog_rows": 1,
        "vectorized": 1,
        "pruned_stale_vectors": 0,
        "remaining": {},
    }


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


def test_memory_repair_plans_and_prunes_orphan_session_vector(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    _init_sessions_db(sessions_db)
    _init_memory_db(memory_db)
    conn = sqlite3.connect(memory_db)
    conn.execute("CREATE TABLE vec_entries (rowid INTEGER PRIMARY KEY)")
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (22, 'session', 'deleted-session', 0, 'orphan', 'ghost-hash', 'ghost-hash', '2026-06-27T09:00:00')
        """
    )
    conn.execute("INSERT INTO vec_entries (rowid) VALUES (22)")
    conn.commit()
    conn.close()
    catalog = MemoryWorkCatalogRepository(str(memory_db))
    catalog.mark(
        source="session",
        source_key="deleted-session",
        item_idx=0,
        content_hash="ghost-hash",
        status="embedded",
        vec_rowid=22,
        reason="test_fixture",
        **session_exchange_embedding_identity().as_catalog_kwargs(),
    )

    report = plan_repairs(sessions_db=str(sessions_db), memory_db=str(memory_db))

    orphan_vectors = [action for action in report.actions if action.action == "stale_vector"]
    assert [action.vec_rowid for action in orphan_vectors] == [22]
    assert report.counts["orphan_catalog_row"] == 1
    assert apply_catalog_repairs(memory_db=str(memory_db), report=report) == 1
    assert prune_stale_vectors(memory_db=str(memory_db), report=report) == 1
    conn = sqlite3.connect(memory_db)
    try:
        assert conn.execute("SELECT 1 FROM vec_meta WHERE rowid=22").fetchone() is None
        assert conn.execute("SELECT 1 FROM vec_entries WHERE rowid=22").fetchone() is None
    finally:
        conn.close()
