from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.memory.retrieval.receipt_source_resolver import MemoryReceiptSourceResolver
from src.tools.hydrate_memory_receipt import (
    _format_exchange_context,
    run,
)


def test_format_exchange_context_anchors_requested_exchange():
    rows = [
        ("user", "primera pregunta"),
        ("assistant", "primera respuesta"),
        ("user", "segunda pregunta"),
        ("assistant", "segunda respuesta"),
        ("user", "tercera pregunta"),
        ("assistant", "tercera respuesta"),
    ]

    output = _format_exchange_context(rows, item_idx=1, window=1)

    assert "Exchange 1 (anchor)" in output
    assert "segunda pregunta" in output
    assert "primera respuesta" in output
    assert "tercera respuesta" in output


def test_load_vector_source_rejects_stale_rowid_and_validates_hash(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT,
            exchange_idx INTEGER,
            text TEXT,
            metadata TEXT,
            created_at TEXT,
            content_hash TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO vec_meta VALUES (1, 'session', 'wrong', 0, 'incorrecto', '{}', '', 'bad')"
    )
    conn.execute(
        "INSERT INTO vec_meta VALUES (2, 'session', 'expected', 3, 'correcto', '{}', '', 'good')"
    )
    conn.commit()
    conn.close()
    receipt = {
        "vec_rowid": 1,
        "source": "session",
        "source_key": "expected",
        "item_idx": 3,
        "content_hash": "good",
    }

    resolver = MemoryReceiptSourceResolver(str(db_path))
    loaded = resolver.load_vector_source(receipt)
    missing = resolver.load_vector_source({**receipt, "content_hash": "stale"})

    assert loaded["rowid"] == 2
    assert loaded["text"] == "correcto"
    assert missing == {}


@pytest.mark.anyio
async def test_hydrate_canonical_memory_uses_full_value_and_touches_receipt():
    load_vector_source = Mock(return_value={"text": "truncated", "metadata": "{}"})
    receipt_repo = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "receipt_id": "mr_123",
                "source": "memory",
                "source_key": "user:workflow",
                "item_idx": 0,
                "vec_rowid": 10,
                "tag": "memory:user:workflow",
                "excerpt": "compact",
                "trigger_query": "workflow",
            }
        ),
        touch_hydrated=AsyncMock(),
        search=AsyncMock(),
    )
    repos = SimpleNamespace(
        memory_receipts=receipt_repo,
        memory=SimpleNamespace(
            receipt_source_resolver=SimpleNamespace(
                load_vector_source=load_vector_source
            ),
            memory_index=SimpleNamespace(
                get=AsyncMock(return_value="Contenido canónico completo y detallado.")
            )
        ),
        messages=SimpleNamespace(get_session_messages=AsyncMock(return_value=[])),
    )

    output = await run(
        receipt_id="mr_123",
        _session_id="current",
        _repos=repos,
    )

    assert "Contenido canónico completo y detallado." in output
    assert "originally activated by: workflow" in output
    load_vector_source.assert_called_once()
    receipt_repo.touch_hydrated.assert_awaited_once_with("current", "mr_123")


@pytest.mark.anyio
async def test_hydrate_session_uses_indexed_exchange_window():
    receipt_repo = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "receipt_id": "mr_long",
                "source": "session",
                "source_key": "past-session",
                "item_idx": 505,
                "vec_rowid": 10,
                "content_hash": "hash",
                "tag": "session:past-session",
                "excerpt": "compact",
                "trigger_query": "tema",
            }
        ),
        touch_hydrated=AsyncMock(),
        search=AsyncMock(),
    )
    get_window = AsyncMock(
        return_value=[
            ("user", "pregunta 504", 504),
            ("assistant", "respuesta 504", 504),
            ("user", "pregunta 505", 505),
            ("assistant", "respuesta 505", 505),
            ("user", "pregunta 506", 506),
        ]
    )
    repos = SimpleNamespace(
        memory_receipts=receipt_repo,
        memory=SimpleNamespace(
            receipt_source_resolver=SimpleNamespace(
                load_vector_source=lambda receipt: {
                    "text": "intercambio vectorizado",
                    "metadata": "{}",
                }
            )
        ),
        messages=SimpleNamespace(get_session_exchange_window=get_window),
    )

    output = await run(
        receipt_id="mr_long",
        context_window=1,
        _session_id="current",
        _repos=repos,
    )

    get_window.assert_awaited_once_with("past-session", 505, 1)
    assert "Exchange 505 (anchor)" in output
    assert "pregunta 504" in output
    assert "pregunta 506" in output


@pytest.mark.anyio
async def test_query_returns_candidate_receipts_when_ambiguous():
    receipt_repo = SimpleNamespace(
        search=AsyncMock(
            return_value=[
                {
                    "receipt_id": "mr_a",
                    "tag": "memory:a",
                    "source": "memory",
                    "source_key": "a",
                    "excerpt": "alpha",
                },
                {
                    "receipt_id": "mr_b",
                    "tag": "session:b",
                    "source": "session",
                    "source_key": "b",
                    "excerpt": "beta",
                },
            ]
        ),
    )
    repos = SimpleNamespace(
        memory_receipts=receipt_repo,
        memory=SimpleNamespace(
            receipt_source_resolver=SimpleNamespace(load_vector_source=lambda receipt: {})
        ),
    )

    output = await run(query="memoria", _session_id="current", _repos=repos)

    assert "[mr_a]" in output
    assert "[mr_b]" in output
    assert "chosen receipt_id" in output
