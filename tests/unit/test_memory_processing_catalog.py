from __future__ import annotations

from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository


def test_processing_catalog_marks_stage_as_processed(tmp_path):
    repo = MemoryProcessingCatalogRepository(str(tmp_path / "memory.db"))

    repo.mark(
        source="session",
        source_key="s1",
        item_idx=-1,
        stage="curated",
        content_hash="abc",
        status="processed",
        processor="curate_sessions",
        reason="no_new_info",
        metadata={"texts": 3},
    )

    row = repo.get(source="session", source_key="s1", item_idx=-1, stage="curated")
    assert row is not None
    assert row["status"] == "processed"
    assert row["processor"] == "curate_sessions"
    assert repo.is_processed(
        source="session",
        source_key="s1",
        item_idx=-1,
        stage="curated",
        content_hash="abc",
    )
    assert not repo.is_processed(
        source="session",
        source_key="s1",
        item_idx=-1,
        stage="curated",
        content_hash="changed",
    )


def test_processing_catalog_tracks_stages_independently(tmp_path):
    repo = MemoryProcessingCatalogRepository(str(tmp_path / "memory.db"))
    base = {
        "source": "session",
        "source_key": "s1",
        "item_idx": -1,
        "content_hash": "abc",
        "status": "processed",
    }

    repo.mark(**base, stage="curated")
    repo.mark(**base, stage="synthesized")

    assert repo.get(source="session", source_key="s1", item_idx=-1, stage="curated")
    assert repo.get(source="session", source_key="s1", item_idx=-1, stage="synthesized")
