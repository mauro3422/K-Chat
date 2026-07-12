import json
import sqlite3

import pytest

from src.memory.curator.memory_inbox import (
    append_memory_inbox_item,
    inbox_embedding_text,
    load_memory_inbox,
    memory_inbox_path,
    vectorize_memory_inbox_items,
)
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository


class FakeInboxStore:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE vec_meta (
                rowid INTEGER PRIMARY KEY,
                source TEXT,
                source_key TEXT,
                exchange_idx INTEGER,
                text TEXT,
                hash TEXT,
                content_hash TEXT,
                source_node_id TEXT DEFAULT ''
            )
            """
        )
        self.inserted: list[dict] = []

    def _get_conn(self):
        return self.conn

    def insert(self, _embedding, **kwargs) -> int:
        rowid = 50 + len(self.inserted)
        self.inserted.append(kwargs)
        self.conn.execute(
            """
            INSERT INTO vec_meta (
                rowid, source, source_key, exchange_idx, text, hash, content_hash, source_node_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                kwargs["source"],
                kwargs["source_key"],
                kwargs["exchange_idx"],
                kwargs["text"],
                kwargs["hash"],
                kwargs["content_hash"],
                kwargs.get("source_node_id", ""),
            ),
        )
        self.conn.commit()
        return rowid

    def close(self) -> None:
        self.conn.close()


def test_memory_inbox_path_uses_daily_partition(tmp_path):
    path = memory_inbox_path("2026-07-02T09:30:00", root=tmp_path)

    assert path == tmp_path / "memory" / "2026" / "07" / "02" / "inbox.jsonl"


def test_append_memory_inbox_item_writes_pending_jsonl(tmp_path):
    payload = append_memory_inbox_item(
        {
            "key": "user:workflow",
            "value": "2026-07-02 10:00 | Mauro wants inbox-first memory.",
            "session_id": "sess-1",
            "channel": "web",
        },
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )

    path = tmp_path / "memory" / "2026" / "07" / "02" / "inbox.jsonl"
    saved = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

    assert payload["inbox_id"]
    assert saved["inbox_id"] == payload["inbox_id"]
    assert saved["status"] == "pending"
    assert saved["source"] == "save_memory"
    assert saved["session_id"] == "sess-1"


def test_load_memory_inbox_skips_invalid_json(tmp_path):
    path = memory_inbox_path("2026-07-02T09:30:00", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"inbox_id":"a"}\nnot-json\n{"inbox_id":"b"}\n', encoding="utf-8")

    items = load_memory_inbox(root=tmp_path)

    assert [item["inbox_id"] for item in items] == ["a", "b"]


def test_load_memory_inbox_limit_zero_reads_all_items(tmp_path):
    for _ in range(105):
        append_memory_inbox_item(
            {"key": "user:workflow", "value": "Mauro wants inbox-first memory."},
            root=tmp_path,
            timestamp="2026-07-02T09:30:00",
        )

    assert len(load_memory_inbox(root=tmp_path)) == 100
    assert len(load_memory_inbox(root=tmp_path, limit=0)) == 105


def test_inbox_embedding_text_includes_context():
    text = inbox_embedding_text(
        {
            "inbox_id": "abc",
            "key": "user:workflow",
            "value": "Mauro wants inbox-first memory.",
            "session_id": "sess-1",
            "channel": "web",
        }
    )

    assert "key: user:workflow" in text
    assert "value: Mauro wants inbox-first memory." in text
    assert "session_id: sess-1" in text


@pytest.mark.anyio
async def test_vectorize_memory_inbox_items_embeds_and_marks_catalog(tmp_path, monkeypatch):
    append_memory_inbox_item(
        {
            "key": "user:workflow",
            "value": "Mauro wants inbox-first memory.",
            "session_id": "sess-1",
            "channel": "web",
        },
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )
    store = FakeInboxStore()
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts: [[0.4] * 384 for _ in texts],
    )

    try:
        result = await vectorize_memory_inbox_items(
            root=tmp_path,
            store=store,
            catalog=catalog,
            source_node_id="pc",
        )
    finally:
        store.close()

    row = catalog.get(source="memory_inbox", source_key=store.inserted[0]["source_key"], item_idx=-1)
    assert result == {"inbox_items": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}
    assert store.inserted[0]["source"] == "memory_inbox"
    assert row is not None
    assert row["status"] == "embedded"
    assert row["pipeline"] == "memory_inbox_embedding"
    assert row["source_node_id"] == "pc"
