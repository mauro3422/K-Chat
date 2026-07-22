import sqlite3

import pytest

from src.memory.entity.linker import EntityLinker, flush_entities_to_db


@pytest.mark.anyio
async def test_flush_entities_updates_existing_id_with_missing_normalized_name(
    tmp_path,
):
    db_path = str(tmp_path / "memory.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT,
                entity_type TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                mention_count INTEGER DEFAULT 1,
                origin_node_id TEXT NOT NULL DEFAULT ''
            )"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX idx_entities_normalized_type
               ON entities(normalized_name, entity_type)"""
        )
        conn.execute(
            """INSERT INTO entities (
                   id, name, normalized_name, entity_type,
                   first_seen, last_seen, mention_count
               ) VALUES ('entity:concept:1', 'memoria', NULL, 'concept', '', '', 4)"""
        )

    linker = EntityLinker(db_path)
    linker.link_exchange([("concept", "memoria", 1.0)], "s1")

    assert await flush_entities_to_db(linker, db_path) == 1
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, normalized_name, mention_count FROM entities"
        ).fetchall()

    assert rows == [("entity:concept:1", "memoria", 5)]
