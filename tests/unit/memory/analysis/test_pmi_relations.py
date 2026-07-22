import sqlite3

from src.memory.analysis.pmi_relations import (
    calculate_pmi_for_session,
    persist_pmi_relations,
)


def test_calculate_pmi_respects_allowed_terms():
    relations, pairs = calculate_pmi_for_session(
        ["memoria ruido grafo memoria ruido grafo"],
        min_cooccurrences=1,
        pmi_threshold=-10,
        allowed_terms={"memoria", "grafo"},
    )

    assert pairs == {("grafo", "memoria")}
    assert {(a, b) for a, b, _ in relations} == {("grafo", "memoria")}


def test_persist_pmi_reuses_typed_entity_case_insensitively(tmp_path):
    db_path = str(tmp_path / "memory.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE entities (
                id TEXT PRIMARY KEY, name TEXT, entity_type TEXT,
                first_seen TEXT, last_seen TEXT, mention_count INTEGER DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE entity_relations (
                source_id TEXT, target_id TEXT, relation_type TEXT, weight REAL,
                first_seen TEXT, last_seen TEXT,
                PRIMARY KEY (source_id, target_id, relation_type)
            )"""
        )
        conn.execute(
            "INSERT INTO entities VALUES ('person:mauro', 'Mauro', 'persona', '', '', 4)"
        )

    assert persist_pmi_relations(db_path, [("mauro", "memoria", 1.2)]) == 1

    with sqlite3.connect(db_path) as conn:
        mauro_rows = conn.execute(
            "SELECT id, entity_type FROM entities WHERE lower(name) = 'mauro'"
        ).fetchall()
        relation = conn.execute(
            "SELECT source_id, target_id FROM entity_relations"
        ).fetchone()

    assert mauro_rows == [("person:mauro", "persona")]
    assert "person:mauro" in relation


def test_persist_pmi_does_not_attach_noise_to_curated_typed_anchor(tmp_path):
    db_path = str(tmp_path / "memory.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE entities (
                id TEXT PRIMARY KEY, name TEXT, entity_type TEXT,
                first_seen TEXT, last_seen TEXT, mention_count INTEGER DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE entity_relations (
                source_id TEXT, target_id TEXT, relation_type TEXT, weight REAL,
                first_seen TEXT, last_seen TEXT,
                PRIMARY KEY (source_id, target_id, relation_type)
            )"""
        )
        conn.execute(
            """CREATE TABLE memory_curated_relations (
                source_id TEXT, target_id TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO entities VALUES (?, ?, ?, '', '', 4)",
            [
                ("project:kchat", "K-Chat", "proyecto"),
                ("tech:sqlite", "SQLite", "tecnologia"),
            ],
        )
        conn.execute(
            "INSERT INTO memory_curated_relations VALUES ('project:kchat', 'tech:sqlite')"
        )

    assert persist_pmi_relations(
        db_path, [("sqlite", "original", 1.2)]
    ) == 0

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM entity_relations").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM entities WHERE name='original'"
        ).fetchone()[0] == 0
