"""Tests for VectorStore (sqlite-vec based embedding store)."""

from __future__ import annotations

import pytest

from src.memory.vector.models import SearchResult, VectorEntry
from src.memory.vector.store import VectorStore


@pytest.fixture
def vector_store(tmp_path):
    db_path = str(tmp_path / "test_vec.db")
    store = VectorStore(db_path)
    store._get_conn()
    yield store
    store.close()


class TestVectorStore:
    def test_init(self, vector_store):
        conn = vector_store._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in tables}
        assert "vec_entries" in names
        assert "vec_meta" in names

    def test_insert_and_search(self, vector_store):
        vec = [0.1] * 384
        rowid = vector_store.insert(
            vec, source="memory", source_key="k1", text="test text"
        )
        assert rowid > 0
        results = vector_store.search(vec, k=10)
        assert len(results) == 1
        assert results[0].entry.id == rowid
        assert results[0].score > 0.9

    def test_search_empty(self, vector_store):
        vec = [0.1] * 384
        results = vector_store.search(vec, k=10)
        assert results == []

    def test_search_with_source_filter(self, vector_store):
        vec = [0.1] * 384
        vector_store.insert(vec, source="memory", source_key="k1", text="mem")
        vector_store.insert(vec, source="session", source_key="s1", text="sess")
        results = vector_store.search(vec, k=10, source_filter="memory")
        assert len(results) == 1
        assert results[0].entry.source == "memory"

    def test_search_max_k(self, vector_store):
        vec = [0.1] * 384
        for i in range(60):
            vector_store.insert(vec, source="test", source_key=f"k{i}", text=str(i))
        results = vector_store.search(vec, k=100)
        assert len(results) <= 50

    def test_find_by_hash(self, vector_store):
        vec = [0.1] * 384
        rowid = vector_store.insert(vec, source="memory", hash="abc123", text="text")
        found = vector_store.find_by_hash("abc123")
        assert found == rowid

    def test_find_by_hash_nonexistent(self, vector_store):
        assert vector_store.find_by_hash("nonexistent") is None

    def test_find_by_hash_with_source(self, vector_store):
        vec = [0.1] * 384
        vector_store.insert(vec, source="memory", hash="abc", text="mem")
        found = vector_store.find_by_hash("abc", source="memory")
        assert found is not None
        assert vector_store.find_by_hash("abc", source="session") is None

    def test_delete(self, vector_store):
        vec = [0.1] * 384
        rowid = vector_store.insert(vec, source="memory", text="text")
        assert vector_store.delete(rowid) is True
        assert vector_store.search(vec, k=10) == []

    def test_delete_nonexistent(self, vector_store):
        assert vector_store.delete(99999) is False

    def test_delete_by_source(self, vector_store):
        vec = [0.1] * 384
        vector_store.insert(vec, source="memory", source_key="my_key", text="a")
        vector_store.insert(vec, source="memory", source_key="my_key", text="b")
        vector_store.insert(vec, source="session", source_key="other", text="c")
        deleted = vector_store.delete_by_source("my_key")
        assert deleted == 2
        assert vector_store.count() == 1

    def test_count(self, vector_store):
        assert vector_store.count() == 0
        vec = [0.1] * 384
        vector_store.insert(vec, source="memory", text="a")
        assert vector_store.count() == 1
        vector_store.insert(vec, source="session", text="b")
        assert vector_store.count() == 2

    def test_count_with_source_filter(self, vector_store):
        vec = [0.1] * 384
        vector_store.insert(vec, source="memory", text="a")
        vector_store.insert(vec, source="session", text="b")
        assert vector_store.count(source="memory") == 1
        assert vector_store.count(source="session") == 1

    def test_insert_with_metadata(self, vector_store):
        vec = [0.1] * 384
        rowid = vector_store.insert(
            vec,
            source="memory",
            source_key="k1",
            text="hello",
            metadata={"lang": "en"},
        )
        assert rowid > 0
        result = vector_store.search(vec, k=10)
        assert len(result) == 1
        assert "lang" in result[0].entry.metadata

    def test_relevance_score_initialized(self, vector_store):
        vec = [0.1] * 384
        rowid = vector_store.insert(vec, source="memory", text="x")
        conn = vector_store._get_conn()
        row = conn.execute(
            "SELECT relevance_score FROM vec_meta WHERE rowid = ?", [rowid]
        ).fetchone()
        assert row is not None
        assert row[0] >= 0.0

    def test_search_returns_proper_types(self, vector_store):
        vec = [0.1] * 384
        vector_store.insert(vec, source="test", text="data")
        results = vector_store.search(vec, k=10)
        assert len(results) > 0
        assert isinstance(results[0], SearchResult)
        assert isinstance(results[0].entry, VectorEntry)

    def test_close(self, tmp_path):
        db_path = str(tmp_path / "close_test.db")
        store = VectorStore(db_path)
        store._get_conn()
        store.close()
        assert store._conn is None
