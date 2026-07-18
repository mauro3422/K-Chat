from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.memory.repos import get_repos
from src.memory.retrieval.receipts import build_memory_receipt, format_receipt_ledger


def test_build_memory_receipt_is_stable_and_compact():
    result = SimpleNamespace(
        rowid=42,
        source="session",
        source_key="past-session",
        item_idx=3,
        content_hash="abc",
        text="A" * 500,
    )

    first = build_memory_receipt("current-session", result, "recordame el diseño")
    second = build_memory_receipt("current-session", result, "otra consulta")

    assert first["receipt_id"] == second["receipt_id"]
    assert first["receipt_id"].startswith("mr_")
    assert len(first["excerpt"]) <= 240
    assert first["item_idx"] == 3
    assert first["vec_rowid"] == 42


def test_format_receipt_ledger_exposes_handles_without_repeating_full_source():
    output = format_receipt_ledger(
        [
            {
                "receipt_id": "mr_123",
                "tag": "session:past",
                "source": "session",
                "source_key": "past",
                "excerpt": "Resumen compacto del recuerdo.",
                "trigger_query": "qué habíamos decidido",
            }
        ],
        total_count=7,
    )

    assert "[mr_123]" in output
    assert "Available receipts in this session: 7" in output
    assert "hydrate_memory_receipt" in output
    assert "Resumen compacto" in output


@pytest.mark.anyio
async def test_memory_receipt_repository_upserts_latest_revision(setup_test_db):
    repos = get_repos()
    await repos.sessions.ensure("s-current")
    receipt = {
        "receipt_id": "mr_123",
        "source": "memory",
        "source_key": "user:workflow",
        "item_idx": 0,
        "vec_rowid": 10,
        "content_hash": "v1",
        "tag": "memory:user:workflow",
        "excerpt": "Primera versión.",
        "trigger_query": "workflow",
    }

    await repos.memory_receipts.upsert_many("s-current", [receipt])
    receipt.update(vec_rowid=11, content_hash="v2", excerpt="Versión nueva.")
    await repos.memory_receipts.upsert_many("s-current", [receipt])

    stored = await repos.memory_receipts.get("s-current", "mr_123")
    assert stored is not None
    assert stored["vec_rowid"] == 11
    assert stored["content_hash"] == "v2"
    assert stored["excerpt"] == "Versión nueva."
    assert stored["injection_count"] == 2
    assert await repos.memory_receipts.count("s-current") == 1
    matches = await repos.memory_receipts.search("s-current", "workflow")
    assert [row["receipt_id"] for row in matches] == ["mr_123"]


@pytest.mark.anyio
async def test_memory_receipts_are_deleted_with_session(setup_test_db):
    repos = get_repos()
    await repos.sessions.ensure("s-delete")
    await repos.memory_receipts.upsert_many(
        "s-delete",
        [
            {
                "receipt_id": "mr_delete",
                "source": "session",
                "source_key": "old",
                "item_idx": 1,
                "vec_rowid": 2,
                "content_hash": "hash",
                "tag": "session:old",
                "excerpt": "old exchange",
                "trigger_query": "old",
            }
        ],
    )

    await repos.sessions.delete("s-delete")

    assert await repos.memory_receipts.count("s-delete") == 0
