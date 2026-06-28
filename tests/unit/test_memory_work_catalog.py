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
