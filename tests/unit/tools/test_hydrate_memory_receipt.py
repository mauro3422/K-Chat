from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.tools.hydrate_memory_receipt import _format_exchange_context, run


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


@pytest.mark.anyio
async def test_hydrate_canonical_memory_uses_full_value_and_touches_receipt():
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
            memory_index=SimpleNamespace(
                get=AsyncMock(return_value="Contenido canónico completo y detallado.")
            )
        ),
        messages=SimpleNamespace(get_session_messages=AsyncMock(return_value=[])),
    )

    with patch(
        "src.tools.hydrate_memory_receipt._load_vector_source",
        return_value={"text": "truncated", "metadata": "{}"},
    ):
        output = await run(
            receipt_id="mr_123",
            _session_id="current",
            _repos=repos,
        )

    assert "Contenido canónico completo y detallado." in output
    assert "originally activated by: workflow" in output
    receipt_repo.touch_hydrated.assert_awaited_once_with("current", "mr_123")


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
    repos = SimpleNamespace(memory_receipts=receipt_repo)

    output = await run(query="memoria", _session_id="current", _repos=repos)

    assert "[mr_a]" in output
    assert "[mr_b]" in output
    assert "chosen receipt_id" in output
