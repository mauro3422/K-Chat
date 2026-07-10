from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from src.memory.curator.context_retrieval import HybridCuratorContextRetriever


@pytest.mark.anyio
async def test_lexical_fallback_returns_only_relevant_memories(tmp_path) -> None:
    db_path = tmp_path / "memory.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE vec_meta (rowid INTEGER PRIMARY KEY, source TEXT, source_key TEXT, text TEXT)"
        )
    memory_path = tmp_path / "MEMORY.md"
    memory_path.write_text(
        "# MEMORY.md\n\n## Memories\n"
        "- **bug:db-query**: 2026-07-10 12:00 | db_query falla al validar columnas.\n"
        "- **user:favorite-color**: 2026-07-10 12:00 | Prefiere azul.\n",
        encoding="utf-8",
    )
    retriever = HybridCuratorContextRetriever(str(db_path), memory_path, top_k=2)

    context = await retriever.retrieve("investigar error de db_query y columnas")

    assert "bug:db-query" in context
    assert "favorite-color" not in context


@pytest.mark.anyio
async def test_lexical_fallback_returns_empty_without_overlap(tmp_path) -> None:
    db_path = tmp_path / "memory.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE vec_meta (rowid INTEGER PRIMARY KEY, source TEXT, source_key TEXT, text TEXT)"
        )
    memory_path = tmp_path / "MEMORY.md"
    memory_path.write_text(
        "# MEMORY.md\n\n## Memories\n- **user:favorite-color**: 2026-07-10 12:00 | Prefiere azul.\n",
        encoding="utf-8",
    )
    retriever = HybridCuratorContextRetriever(str(db_path), memory_path)

    context = await retriever.retrieve("diagnosticar sqlite vector index")

    assert context == ""


def test_hybrid_selection_requires_keyword_or_entity_evidence(tmp_path) -> None:
    retriever = HybridCuratorContextRetriever(
        str(tmp_path / "memory.db"),
        tmp_path / "MEMORY.md",
        top_k=2,
    )
    supported = retriever._select_supported_results(
        [
            SimpleNamespace(source_key="vector-only", vector_score=0.9, keyword_score=0.0, entity_score=0.0, fusion_score=0.9),
            SimpleNamespace(source_key="weak-keyword", vector_score=0.0, keyword_score=0.13, entity_score=0.0, fusion_score=0.1),
            SimpleNamespace(source_key="strong-keyword", vector_score=0.0, keyword_score=0.8, entity_score=0.0, fusion_score=0.05),
            SimpleNamespace(source_key="entity", vector_score=0.0, keyword_score=0.0, entity_score=0.4, fusion_score=0.04),
        ]
    )

    assert [result.source_key for result in supported] == ["strong-keyword", "weak-keyword"]
