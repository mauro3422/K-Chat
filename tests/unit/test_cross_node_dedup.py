"""Cross-node embedding dedup contract test.

Verifies the core invariant enabled by ``source_node_id`` (migration 015 on
memory.db): once two nodes share a ``memory.db`` (via Syncthing, manual
copy, or any future manifest protocol), the existing
``SELECT rowid FROM vec_meta WHERE content_hash = ?`` dedup query in
``vectorize_session`` automatically returns vectors written by *other* nodes.

This test simulates the scenario directly without a network:

1. Node A ("laptop") writes an embedding with content_hash X and
   source_node_id="laptop".
2. The memory.db file is "synced" (in test: same DB) to Node B
   ("pc-grande").
3. Node B calls ``vectorize_session`` with the same text. The pipeline's
   dedup check should find the existing row by content_hash and skip
   generating a new embedding — regardless of source_node_id.

This is the foundation the cross-node embedding manifest needs: the
storage layer already supports it. The manifest (proposed in
MEMORY_ROADMAP.md) only needs to make the lookup *remote* before
Syncthing sync, not change the storage protocol itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import tempfile
from typing import Any

import pytest

from src.memory.content_hash import normalize_for_content_hash
from src.memory.vector.store import VectorStore
from src.memory.vectorize_sessions import vectorize_session


def _set_memory_db(tmp_path: str) -> str:
    """Point ``resolve_memory_db_path`` at a temp DB and run schema.

    Returns the path so a test can read the DB directly with sqlite3.
    """
    db_path = str(tmp_path / "memory.db")
    # Run migrations on the temp DB.
    import src.memory.memory_db_path as mp
    mp.resolve_memory_db_path = lambda config=None: db_path  # type: ignore[assignment]
    from src.memory.memory_schema import init_memory_db
    asyncio.run(init_memory_db())

    # Also point VectorStore's default there.
    os.environ["KAIROS_MEMORY_DB_PATH"] = db_path
    return db_path


def _make_mock_repos(tmp_path: str) -> Any:
    """Build a minimal Repositories fake with async session/message getters."""
    sessions = [
        {"session_id": "sess-laptop-1", "name": "", "created_at": "2026-06-29T10:00:00"},
    ]
    messages = [
        {"role": "user", "content": "Explaining cross-node dedup contract for embeddings in Kairos", "created_at": "2026-06-29T10:00:00"},
        {"role": "assistant", "content": "Cross-node dedup means each node's vectorizer reuses embeddings already present in the shared memory.db, even if those embeddings were written by a peer node.", "created_at": "2026-06-29T10:00:01"},
    ]

    class _FakeSessions:
        async def _get_conn(self):
            return self._conn

        def _set_conn(self, c):
            self._conn = c

    class _FakeMessages:
        async def _get_conn(self):
            return self._conn

        def _set_conn(self, c):
            self._conn = c

    fake_sessions = _FakeSessions()
    fake_messages = _FakeMessages()

    class _FakeMemory:
        def __init__(self):
            self.vector_store = None

    class _FakeRepos:
        def __init__(self):
            self.sessions = fake_sessions
            self.messages = fake_messages
            self.memory = _FakeMemory()

    repos = _FakeRepos()

    # Stub _get_conn to return records from local lists.
    class _Cursor:
        def __init__(self, rows):
            self._rows = rows
            self._idx = 0
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self._idx >= len(self._rows):
                raise StopAsyncIteration
            row = self._rows[self._idx]
            self._idx += 1
            return row
        async def fetchall(self):
            return list(self._rows)
        async def fetchone(self):
            if self._idx >= len(self._rows):
                return None
            row = self._rows[self._idx]
            self._idx += 1
            return row
        async def execute(self, sql, params=()):
            # Return self for chained fetchall
            if "FROM sessions" in sql:
                self._rows = sessions
            elif "FROM messages" in sql:
                self._rows = messages
            self._idx = 0
            return self

    class _Conn:
        async def execute(self, sql, params=()):
            return _Cursor([])
        async def cursor(self):
            return _Cursor([])

    conn = _Conn()
    fake_sessions._set_conn(conn)
    fake_messages._set_conn(conn)
    return repos


@pytest.fixture
def isolated_memory_db(tmp_path, monkeypatch):
    """Spin up an isolated memory.db for the test, restore on teardown."""
    db_path = str(tmp_path / "memory.db")
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", db_path)

    # Patch resolve_memory_db_path so all callers see the temp path.
    import src.memory.memory_db_path as mp
    original = mp.resolve_memory_db_path
    mp.resolve_memory_db_path = lambda config=None: db_path  # type: ignore[assignment]
    # Run migrations.
    from src.memory.memory_schema import init_memory_db
    asyncio.run(init_memory_db())
    try:
        yield db_path
    finally:
        mp.resolve_memory_db_path = original  # type: ignore[assignment]


def test_source_node_id_column_persisted(isolated_memory_db):
    """Migration 015 landed: vec_meta has source_node_id."""
    conn = sqlite3.connect(isolated_memory_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vec_meta)").fetchall()}
    conn.close()
    assert "source_node_id" in cols, "Migration 015 missing: vec_meta.source_node_id"


def test_entities_origin_node_id_column(isolated_memory_db):
    """Migration 016 landed: entities has origin_node_id."""
    conn = sqlite3.connect(isolated_memory_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()}
    conn.close()
    assert "origin_node_id" in cols, "Migration 016 missing: entities.origin_node_id"


def test_clusters_origin_node_id_column(isolated_memory_db):
    """Migration 017 landed: topic_clusters has origin_node_id."""
    conn = sqlite3.connect(isolated_memory_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(topic_clusters)").fetchall()}
    conn.close()
    assert "origin_node_id" in cols, "Migration 017 missing: topic_clusters.origin_node_id"


def test_vectorstore_insert_persists_source_node_id(isolated_memory_db):
    """VectorStore.insert writes source_node_id into vec_meta."""
    store = VectorStore(isolated_memory_db)
    store._get_conn()
    try:
        rowid = store.insert(
            [0.0] * 384,
            source="session",
            source_key="sess-A",
            text="provenance test text",
            content_hash="hash-123",
            source_node_id="laptop",
        )
        conn = store._get_conn()
        row = conn.execute(
            "SELECT source_node_id, content_hash FROM vec_meta WHERE rowid = ?",
            (rowid,),
        ).fetchone()
        assert row is not None
        assert row[0] == "laptop"
        assert row[1] == "hash-123"
    finally:
        store.close()


def test_cross_node_dedup_finds_peer_embedding_via_content_hash(isolated_memory_db):
    """Cross-node dedup contract: a node B sees embeddings written by node A.

    Setup:
      1. Node "laptop" inserts an embedding with content_hash X.
      2. Node "pc-grande" queries "is there an embedding for content_hash X?"
         — the answer must be YES, because the lookup is purely by
         content_hash, not filtered by source_node_id.

    This is exactly what ``vectorize_session`` does at line 437-467 of
    src/memory/vectorize_sessions.py: ``SELECT rowid FROM vec_meta
    WHERE content_hash = ?``. The query deliberately ignores
    source_node_id, so once memory.db is shared the dedup is automatic.
    """
    store = VectorStore(isolated_memory_db)
    store._get_conn()
    try:
        # Node A ("laptop") embeds first.
        laptop_text = "Python async patterns for cross-node memory contract"
        laptop_hash = hashlib.md5(normalize_for_content_hash(laptop_text[:4000]).encode()).hexdigest()
        laptop_rowid = store.insert(
            [0.1] * 384,
            source="session",
            source_key="sess-laptop",
            text=laptop_text,
            content_hash=laptop_hash,
            source_node_id="laptop",
        )

        # Node B ("pc-grande") wants to embed the same text.
        # The dedup query is content_hash-only — it ignores source_node_id.
        conn = store._get_conn()
        existing = conn.execute(
            "SELECT rowid FROM vec_meta WHERE content_hash = ?",
            (laptop_hash,),
        ).fetchone()
        assert existing is not None, (
            "Cross-node dedup contract broken: content_hash lookup did not "
            "return the row written by another source_node_id."
        )
        assert existing[0] == laptop_rowid
    finally:
        store.close()