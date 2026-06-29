import os
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


class _CacheStore:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE vec_meta (
                rowid INTEGER PRIMARY KEY,
                source TEXT,
                source_key TEXT,
                exchange_idx INTEGER DEFAULT 0,
                text TEXT,
                hash TEXT,
                content_hash TEXT,
                created_at TEXT DEFAULT ''
            )
            """
        )
        self.deleted: list[tuple[str, str]] = []
        self.inserted: list[dict] = []

    def _get_conn(self):
        return self.conn

    def delete_by_source(self, source_key: str, source: str = "") -> int:
        self.deleted.append((source, source_key))
        return 0

    def insert(self, embedding, **kwargs) -> int:
        rowid = 100 + len(self.inserted)
        self.inserted.append(kwargs)
        self.conn.execute(
            """
            INSERT INTO vec_meta (rowid, source, source_key, text, hash, content_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                kwargs["source"],
                kwargs["source_key"],
                kwargs["text"],
                kwargs["hash"],
                kwargs["content_hash"],
            ),
        )
        self.conn.commit()
        return rowid

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM vec_meta").fetchone()[0]

    def close(self) -> None:
        self.conn.close()


@pytest.fixture
def cache_store():
    store = _CacheStore()
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def temp_memory_file():
    temp_dir = tempfile.mkdtemp()
    temp_filepath = os.path.join(temp_dir, "MEMORY.md")
    with open(temp_filepath, "w", encoding="utf-8") as f:
        f.write("# MEMORY.md\n\nUser: \nSystem: test-user\n\n")

    with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
        yield temp_filepath

    try:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        os.rmdir(temp_dir)
    except Exception:
        pass


@pytest.mark.anyio
async def test_reindex_memories_skips_current_memory_embedding(cache_store, monkeypatch):
    from src.memory.content_hash import memory_hashes
    from src.memory.operations.reindex import _reindex_memories

    key = "user:lenguaje"
    value = "Mauro usa Python para scripts de memoria."
    raw_hash, content_hash = memory_hashes(value)
    store = cache_store
    store.conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, text, hash, content_hash)
        VALUES (7, 'memory', ?, ?, ?, '')
        """,
        (key, value, raw_hash),
    )
    store.conn.commit()
    repos = SimpleNamespace(
        memory=SimpleNamespace(
            memory_index=SimpleNamespace(get_all=AsyncMock(return_value=[{"key": key, "value": value}])),
            vector_store=store,
        )
    )

    def fail_generate_embedding(_text):
        raise AssertionError("embedding should be reused")

    monkeypatch.setattr("src.memory.embeddings.service.generate_embedding", fail_generate_embedding)

    result = await _reindex_memories(dry_run=False, repos=repos)

    assert "0 entradas" in result
    assert "1 sin cambios" in result
    assert store.deleted == []
    assert store.inserted == []
    row = store.conn.execute("SELECT hash, content_hash FROM vec_meta WHERE rowid = 7").fetchone()
    assert row == (raw_hash, content_hash)


@pytest.mark.anyio
async def test_save_memory_skips_current_memory_embedding(temp_memory_file, cache_store, monkeypatch):
    from src.memory.content_hash import memory_hashes
    from src.tools.save_memory import run as save_memory_run

    key = "user:lenguaje"
    value = "Mauro usa Python para scripts de memoria."
    raw_hash, _content_hash = memory_hashes(value)
    store = cache_store
    store.conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, text, hash, content_hash)
        VALUES (7, 'memory', ?, ?, ?, '')
        """,
        (key, value, raw_hash),
    )
    store.conn.commit()
    repos = SimpleNamespace(
        memory=SimpleNamespace(
            memory_index=SimpleNamespace(upsert=AsyncMock(return_value=True), delete=AsyncMock(), get=AsyncMock()),
            vector_store=store,
        )
    )

    def fail_generate_embedding(_text):
        raise AssertionError("embedding should be reused")

    monkeypatch.setattr("src.memory.embeddings.service.generate_embedding", fail_generate_embedding)

    result = await save_memory_run(key=key, value=value, _repos=repos)

    assert "[OK]" in result
    assert store.deleted == []
    assert store.inserted == []
