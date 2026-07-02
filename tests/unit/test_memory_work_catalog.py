from __future__ import annotations

from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository


def test_work_catalog_marks_deduped_item_as_processed(tmp_path):
    repo = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))

    repo.mark(
        source="session",
        source_key="s1",
        item_idx=2,
        content_hash="abc",
        status="deduped",
        vec_rowid=42,
        reason="content_hash",
    )

    row = repo.get(source="session", source_key="s1", item_idx=2)
    assert row is not None
    assert row["status"] == "deduped"
    assert row["vec_rowid"] == 42
    assert repo.is_processed(source="session", source_key="s1", item_idx=2, content_hash="abc")
    assert not repo.is_processed(source="session", source_key="s1", item_idx=2, content_hash="changed")


def test_work_catalog_max_processed_idx_ignores_pending(tmp_path):
    repo = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    repo.mark(source="session", source_key="s1", item_idx=1, content_hash="a", status="embedded")
    repo.mark(source="session", source_key="s1", item_idx=3, content_hash="b", status="pending")

    assert repo.max_processed_idx(source="session", source_key="s1") == 1


def test_work_catalog_keeps_independent_pipeline_model_decisions(tmp_path):
    repo = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))

    repo.mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash="same-content",
        status="embedded",
        pipeline="session_exchange_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )
    repo.mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash="same-content",
        status="embedded",
        vec_rowid=99,
        pipeline="session_exchange_embedding",
        pipeline_version="1",
        model_id="next-embedding-model",
        model_version="default",
    )

    assert repo.is_processed(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash="same-content",
        pipeline="session_exchange_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )
    next_row = repo.get(
        source="session",
        source_key="s1",
        item_idx=0,
        pipeline="session_exchange_embedding",
        pipeline_version="1",
        model_id="next-embedding-model",
        model_version="default",
    )
    assert next_row is not None
    assert next_row["vec_rowid"] == 99


def test_work_catalog_migrates_legacy_primary_key(tmp_path):
    db_path = tmp_path / "memory.db"
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE memory_work_catalog (
            source TEXT NOT NULL,
            source_key TEXT NOT NULL,
            item_idx INTEGER NOT NULL,
            content_hash TEXT NOT NULL DEFAULT '',
            pipeline TEXT NOT NULL DEFAULT 'embedding',
            pipeline_version TEXT NOT NULL DEFAULT '1',
            model_id TEXT NOT NULL DEFAULT 'fastembed-default',
            model_version TEXT NOT NULL DEFAULT 'default',
            source_node_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            vec_rowid INTEGER,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (source, source_key, item_idx)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO memory_work_catalog (
            source, source_key, item_idx, content_hash, status
        ) VALUES ('session', 's1', 0, 'old', 'embedded')
        """
    )
    conn.commit()
    conn.close()

    repo = MemoryWorkCatalogRepository(str(db_path))
    repo.mark(
        source="session",
        source_key="s1",
        item_idx=0,
        content_hash="new",
        status="embedded",
        pipeline="session_exchange_embedding",
        pipeline_version="1",
        model_id="other-model",
        model_version="default",
    )

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT pipeline, model_id, content_hash FROM memory_work_catalog").fetchall()
    pk_cols = [
        row[1]
        for row in sorted(
            (row for row in conn.execute("PRAGMA table_info(memory_work_catalog)") if row[5]),
            key=lambda row: row[5],
        )
    ]
    conn.close()

    assert pk_cols == ["source", "source_key", "item_idx", "pipeline", "pipeline_version", "model_id", "model_version"]
    assert len(rows) == 2
