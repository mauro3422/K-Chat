import sqlite3

import aiosqlite
import pytest

from src.memory.repos_memory.entity_repo import EntityRepository


@pytest.mark.anyio
async def test_upsert_relation_materializes_non_entity_graph_nodes(tmp_path):
    db_path = str(tmp_path / "memory.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """CREATE TABLE entities (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, entity_type TEXT NOT NULL,
                metadata TEXT DEFAULT '{}', first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL, mention_count INTEGER DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE entity_relations (
                source_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL, weight REAL,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                PRIMARY KEY (source_id, target_id, relation_type)
            )"""
        )

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    repo = EntityRepository(conn=conn)
    try:
        await repo.upsert_relation(
            "inbox:item-1",
            "memory:user:lenguaje",
            "PROMOTED_TO",
            timestamp="2026-07-19T02:00:00",
        )
        nodes = await conn.execute_fetchall(
            "SELECT id, entity_type FROM entities ORDER BY id"
        )
        relation = await conn.execute_fetchall(
            "SELECT source_id, target_id, relation_type FROM entity_relations"
        )
    finally:
        await conn.close()

    assert [tuple(row) for row in nodes] == [
        ("inbox:item-1", "inbox"),
        ("memory:user:lenguaje", "memory"),
    ]
    assert [tuple(row) for row in relation] == [
        ("inbox:item-1", "memory:user:lenguaje", "PROMOTED_TO")
    ]
