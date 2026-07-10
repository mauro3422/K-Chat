from __future__ import annotations

import sqlite3

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
