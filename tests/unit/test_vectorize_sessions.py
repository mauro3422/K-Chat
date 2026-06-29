"""Smoke tests for vectorize_sessions module — pure functions only."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from src.memory.noise_filter import is_noise
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.vectorize_sessions import _normalize_for_dedup, group_into_exchanges, vectorize_session


class _FakeStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.inserts: list[dict] = []

    def _get_conn(self) -> sqlite3.Connection:
        return self.conn

    def insert(self, embedding, **kwargs) -> int:
        rowid = 100 + len(self.inserts)
        self.inserts.append(kwargs)
        self.conn.execute(
            """
            INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                rowid,
                kwargs["source"],
                kwargs["source_key"],
                kwargs["exchange_idx"],
                kwargs["text"],
                kwargs["hash"],
                kwargs["content_hash"],
            ),
        )
        self.conn.commit()
        return rowid


@pytest.fixture
def vec_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    try:
        yield conn
    finally:
        conn.close()


class TestGroupIntoExchanges:
    def test_empty_list_returns_empty(self):
        assert group_into_exchanges([]) == []

    def test_single_user_message_returns_one_exchange(self):
        messages = [{"role": "user", "content": "hello"}]
        result = group_into_exchanges(messages)
        assert len(result) == 1
        assert "User: hello" in result[0]["text"]
        assert "Assistant: _pending_" in result[0]["text"]

    def test_user_assistant_pair_returns_one_exchange(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = group_into_exchanges(messages)
        assert len(result) == 1
        assert "User: hello" in result[0]["text"]
        assert "Assistant: hi there" in result[0]["text"]

    def test_user_tool_assistant_returns_one_exchange(self):
        messages = [
            {"role": "user", "content": "search for x"},
            {"role": "tool", "content": "result 1\nresult 2"},
            {"role": "assistant", "content": "here are the results"},
        ]
        result = group_into_exchanges(messages)
        assert len(result) == 1
        assert "Assistant: here are the results" in result[0]["text"]

    def test_multiple_exchanges_returns_correct_count(self):
        messages = [
            {"role": "user", "content": "first q"},
            {"role": "assistant", "content": "first a"},
            {"role": "user", "content": "second q"},
            {"role": "assistant", "content": "second a"},
            {"role": "user", "content": "third q"},
        ]
        result = group_into_exchanges(messages)
        assert len(result) == 3


class TestNormalizeForDedup:
    def test_lowercases(self):
        assert _normalize_for_dedup("HELLO WORLD") == "hello world"

    def test_removes_code_blocks(self):
        text = "some text ```python\nprint('hello')\n``` more text"
        result = _normalize_for_dedup(text)
        assert "print" not in result
        assert "some text" in result
        assert "more text" in result

    def test_collapses_whitespace(self):
        text = "hello    world\n\n  foo"
        result = _normalize_for_dedup(text)
        assert result == "hello world foo"


class TestIsNoise:
    def test_short_text_returns_true(self):
        noisy, reason = is_noise("hi", role="user")
        assert noisy is True

    def test_meaningful_text_returns_false(self):
        text = (
            "This is a meaningful query about how to implement a sorting "
            "algorithm in Python. I need to understand the complexity analysis."
        )
        noisy, reason = is_noise(text, role="user")
        assert noisy is False


@pytest.mark.asyncio
async def test_vectorize_session_catalog_marks_cross_session_dedup(tmp_path, monkeypatch, vec_conn):
    text = (
        "User: Explain how a distributed memory catalog avoids duplicated embedding work "
        "between two Kairos nodes.\n"
        "Assistant: It tracks each logical source item separately from the physical vector row."
    )
    text_hash = hashlib.md5(_normalize_for_dedup(text[:4000]).encode()).hexdigest()
    conn = vec_conn
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
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (7, 'session', 'session-a', 0, ?, ?, ?, datetime('now'))
        """,
        (text, text_hash, text_hash),
    )
    conn.commit()
    store = _FakeStore(conn)
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    repos = SimpleNamespace(memory=SimpleNamespace(work_catalog=catalog))

    async def fake_get_session_messages(session_id, repos=None):
        return [
            {"role": "user", "content": text.split("\nAssistant: ")[0].removeprefix("User: "), "created_at": "now"},
            {"role": "assistant", "content": text.split("\nAssistant: ")[1], "created_at": "now"},
        ]

    monkeypatch.setattr("src.memory.vectorize_sessions.get_session_messages", fake_get_session_messages)

    count, noise_count, mappings, entities = await vectorize_session("session-b", repos=repos, store=store)
    assert count == 1
    assert noise_count == 0
    assert store.inserts == []

    row = catalog.get(source="session", source_key="session-b", item_idx=0)
    assert row is not None
    assert row["status"] == "deduped"
    assert row["vec_rowid"] == 7

    count, noise_count, mappings, entities = await vectorize_session("session-b", repos=repos, store=store)
    assert count == 0
    assert noise_count == 0
    assert store.inserts == []


@pytest.mark.asyncio
async def test_vectorize_session_catalog_does_not_trust_legacy_exchange_idx(tmp_path, monkeypatch, vec_conn):
    old_text = "User: old question about memory.\nAssistant: old answer."
    new_text = (
        "User: Explain why exchange indexes alone are not enough for memory freshness.\n"
        "Assistant: The content hash must match, otherwise the previous vector is stale."
    )
    old_hash = hashlib.md5(_normalize_for_dedup(old_text[:4000]).encode()).hexdigest()
    conn = vec_conn
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
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (8, 'session', 'session-b', 0, ?, ?, ?, datetime('now'))
        """,
        (old_text, old_hash, old_hash),
    )
    conn.commit()
    store = _FakeStore(conn)
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    repos = SimpleNamespace(memory=SimpleNamespace(work_catalog=catalog))

    async def fake_get_session_messages(session_id, repos=None):
        return [
            {"role": "user", "content": new_text.split("\nAssistant: ")[0].removeprefix("User: "), "created_at": "now"},
            {"role": "assistant", "content": new_text.split("\nAssistant: ")[1], "created_at": "now"},
        ]

    monkeypatch.setattr("src.memory.vectorize_sessions.get_session_messages", fake_get_session_messages)
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts: [[0.1] * 384 for _ in texts],
    )

    count, noise_count, mappings, entities = await vectorize_session("session-b", repos=repos, store=store)
    assert count == 1
    assert noise_count == 0
    assert len(store.inserts) == 1

    row = catalog.get(source="session", source_key="session-b", item_idx=0)
    assert row is not None
    assert row["status"] == "embedded"
    assert row["vec_rowid"] == 100


@pytest.mark.asyncio
async def test_vectorize_session_can_fill_targeted_gap_with_existing_later_index(tmp_path, monkeypatch, vec_conn):
    texts = [
        (
            "User: Explain how targeted memory repair fills an old missing exchange.\n"
            "Assistant: It embeds the exact exchange index instead of trusting max index cursors."
        ),
        (
            "User: Explain why unrelated exchanges must remain untouched during repair.\n"
            "Assistant: The repair plan limits vectorization to the explicitly missing indexes."
        ),
        (
            "User: Explain why later vectors can hide earlier gaps in a session.\n"
            "Assistant: A max exchange index cursor can skip older missing vectors."
        ),
    ]
    conn = vec_conn
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
    later_hash = hashlib.md5(_normalize_for_dedup(texts[2][:4000]).encode()).hexdigest()
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (9, 'session', 'session-gap', 2, ?, ?, ?, datetime('now'))
        """,
        (texts[2], later_hash, later_hash),
    )
    conn.commit()
    store = _FakeStore(conn)
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    broken_hash = hashlib.md5(_normalize_for_dedup(texts[0][:4000]).encode()).hexdigest()
    catalog.mark(
        source="session",
        source_key="session-gap",
        item_idx=0,
        content_hash=broken_hash,
        status="embedded",
        vec_rowid=8,
        reason="old_row",
    )
    repos = SimpleNamespace(memory=SimpleNamespace(work_catalog=catalog))

    async def fake_get_session_messages(session_id, repos=None):
        messages = []
        for text in texts:
            user_text, assistant_text = text.split("\nAssistant: ")
            messages.extend([
                {"role": "user", "content": user_text.removeprefix("User: "), "created_at": "now"},
                {"role": "assistant", "content": assistant_text, "created_at": "now"},
            ])
        return messages

    monkeypatch.setattr("src.memory.vectorize_sessions.get_session_messages", fake_get_session_messages)
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts_to_embed: [[0.1] * 384 for _ in texts_to_embed],
    )

    count, noise_count, mappings, entities = await vectorize_session(
        "session-gap",
        repos=repos,
        store=store,
        exchange_indexes={0},
    )
    assert count == 1
    assert noise_count == 0
    assert [insert["exchange_idx"] for insert in store.inserts] == [0]

    row = catalog.get(source="session", source_key="session-gap", item_idx=0)
    assert row is not None
    assert row["status"] == "embedded"
    assert row["vec_rowid"] == 100


@pytest.mark.asyncio
async def test_vectorize_session_requires_work_catalog(monkeypatch, vec_conn):
    conn = vec_conn
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
    store = _FakeStore(conn)

    async def fake_get_session_messages(session_id, repos=None):
        return [
            {"role": "user", "content": "Explain catalog authority for embeddings.", "created_at": "now"},
            {"role": "assistant", "content": "The work catalog is required.", "created_at": "now"},
        ]

    monkeypatch.setattr("src.memory.vectorize_sessions.get_session_messages", fake_get_session_messages)
    monkeypatch.setattr("src.memory.vectorize_sessions._get_work_catalog", lambda repos=None: None)

    with pytest.raises(RuntimeError, match="memory_work_catalog is required"):
        await vectorize_session("session-no-catalog", store=store)
