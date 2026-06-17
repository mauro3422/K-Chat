"""Tests for relation detection between topic clusters.

Tests detect_relations and flush_relations_to_db in isolation,
using raw dicts as input (not HeuristicClusterer objects).
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from src.memory.clustering.relations import detect_relations, flush_relations_to_db


_TOPIC_RELATIONS_DDL = """
CREATE TABLE IF NOT EXISTS topic_relations (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    shared_keywords TEXT NOT NULL DEFAULT '[]',
    shared_count INTEGER NOT NULL DEFAULT 0,
    relationship_type TEXT NOT NULL DEFAULT 'related',
    weight REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source_id, target_id)
)
"""


def _make_cluster(cid: str, words: list[str]) -> dict:
    """Build a cluster dict as produced by Cluster.as_dict."""
    return {
        "id": cid,
        "keywords": [(w, 1.0) for w in words],
    }


# ── detect_relations ────────────────────────────────────────────────

class TestDetectRelations:
    def test_empty_clusters_list(self):
        assert detect_relations([]) == []

    def test_single_cluster(self):
        clusters = [_make_cluster("c1", ["python", "code"])]
        assert detect_relations(clusters) == []

    def test_two_clusters_no_shared_keywords(self):
        clusters = [
            _make_cluster("c1", ["python", "code"]),
            _make_cluster("c2", ["cooking", "recipe"]),
        ]
        assert detect_relations(clusters) == []

    def test_two_clusters_with_shared_keywords(self):
        clusters = [
            _make_cluster("c1", ["python", "code", "function"]),
            _make_cluster("c2", ["python", "code", "cooking"]),
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 1
        rel = rels[0]
        assert rel["source_id"] in ("c1", "c2")
        assert rel["target_id"] in ("c1", "c2")
        assert rel["source_id"] != rel["target_id"]
        assert set(rel["shared_keywords"]) == {"python", "code"}
        assert rel["shared_count"] == 2
        assert 0 < rel["weight"] <= 1.0

    def test_three_clusters_chain(self):
        """c1↔c2 and c2↔c3 share 2+ keywords; c1↔c3 do not."""
        clusters = [
            _make_cluster("c1", ["a", "b", "c"]),
            _make_cluster("c2", ["a", "b", "d"]),
            _make_cluster("c3", ["b", "d", "e", "f"]),
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 2
        pairs = {(r["source_id"], r["target_id"]) for r in rels}
        assert ("c1", "c2") in pairs or ("c2", "c1") in pairs
        assert ("c2", "c3") in pairs or ("c3", "c2") in pairs

    def test_no_duplicate_pairs(self):
        """Each pair appears only once, regardless of keyword overlap."""
        clusters = [
            _make_cluster("c1", ["a", "b"]),
            _make_cluster("c2", ["a", "b"]),
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 1


# ── Relation attributes ─────────────────────────────────────────────

class TestRelationAttributes:
    def test_relationship_type_related(self):
        """2 shared keywords → 'related'."""
        clusters = [
            _make_cluster("c1", ["a", "b", "c", "d"]),
            _make_cluster("c2", ["a", "b", "x", "y"]),
        ]
        rel = detect_relations(clusters)[0]
        assert rel["shared_count"] == 2
        assert rel["relationship_type"] == "related"

    def test_relationship_type_strongly_related(self):
        """3+ shared keywords → 'strongly_related'."""
        clusters = [
            _make_cluster("c1", ["a", "b", "c", "d"]),
            _make_cluster("c2", ["a", "b", "c", "x"]),
        ]
        rel = detect_relations(clusters)[0]
        assert rel["shared_count"] == 3
        assert rel["relationship_type"] == "strongly_related"

    def test_shared_keywords_is_list_of_strings(self):
        clusters = [
            _make_cluster("c1", ["python", "code"]),
            _make_cluster("c2", ["python", "code", "cooking"]),
        ]
        rel = detect_relations(clusters)[0]
        assert isinstance(rel["shared_keywords"], list)
        assert all(isinstance(kw, str) for kw in rel["shared_keywords"])

    def test_weight_in_range(self):
        clusters = [
            _make_cluster("c1", ["a", "b", "c", "d"]),
            _make_cluster("c2", ["a", "b", "x", "y"]),
        ]
        rel = detect_relations(clusters)[0]
        assert 0.0 < rel["weight"] <= 1.0

    def test_weight_is_jaccard_of_keyword_sets(self):
        clusters = [
            _make_cluster("c1", ["a", "b", "c"]),
            _make_cluster("c2", ["a", "b", "d", "e"]),
        ]
        rel = detect_relations(clusters)[0]
        expected = 2 / 5  # {a,b} / {a,b,c,d,e}
        assert rel["weight"] == pytest.approx(expected)

    def test_dict_format_keywords(self):
        """Also accept list-of-dict format (Cluster.as_dict alternative)."""
        clusters = [
            {
                "id": "c1",
                "keywords": [{"word": "python", "score": 1.0}, {"word": "code", "score": 0.8}, {"word": "function", "score": 0.6}],
            },
            {
                "id": "c2",
                "keywords": [{"word": "python", "score": 0.5}, {"word": "code", "score": 0.4}, {"word": "cooking", "score": 1.0}],
            },
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 1
        assert rels[0]["shared_count"] == 2


# ── flush_relations_to_db ───────────────────────────────────────────

class TestFlushRelationsToDB:
    def _create_schema(self, conn: sqlite3.Connection):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(_TOPIC_RELATIONS_DDL)
        conn.commit()

    @pytest.mark.asyncio
    async def test_flush_empty_list(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        count = await flush_relations_to_db([], db)
        assert count == 0

        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT COUNT(*) FROM topic_relations").fetchone()
        assert rows[0] == 0
        conn.close()

    @pytest.mark.asyncio
    async def test_flush_writes_relations(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        relations = [
            {
                "source_id": "c1",
                "target_id": "c2",
                "shared_keywords": ["python", "code"],
                "shared_count": 2,
                "relationship_type": "related",
                "weight": 0.5,
            },
            {
                "source_id": "c2",
                "target_id": "c3",
                "shared_keywords": ["a", "b", "c"],
                "shared_count": 3,
                "relationship_type": "strongly_related",
                "weight": 0.75,
            },
        ]
        count = await flush_relations_to_db(relations, db)
        assert count == 2

        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT source_id, target_id, shared_count, relationship_type, weight FROM topic_relations ORDER BY source_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "c1"
        assert rows[0][1] == "c2"
        assert rows[0][2] == 2
        assert rows[0][3] == "related"
        assert rows[0][4] == 0.5
        assert rows[1][0] == "c2"
        assert rows[1][1] == "c3"
        assert rows[1][3] == "strongly_related"
        conn.close()

    @pytest.mark.asyncio
    async def test_flush_shared_keywords_json(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        relations = [
            {
                "source_id": "c1",
                "target_id": "c2",
                "shared_keywords": ["python", "code", "function"],
                "shared_count": 3,
                "relationship_type": "related",
                "weight": 0.6,
            },
        ]
        await flush_relations_to_db(relations, db)

        conn = sqlite3.connect(db)
        row = conn.execute("SELECT shared_keywords FROM topic_relations").fetchone()
        parsed = json.loads(row[0])
        assert parsed == ["python", "code", "function"]
        conn.close()

    @pytest.mark.asyncio
    async def test_flush_no_op_on_duplicate(self, tmp_path):
        """INSERT OR IGNORE means duplicate PK is silently skipped, but count
        unconditionally increments in the source. Verify the DB only has 1 row."""
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        rel = {
            "source_id": "c1",
            "target_id": "c2",
            "shared_keywords": ["python"],
            "shared_count": 1,
            "relationship_type": "related",
            "weight": 0.3,
        }
        await flush_relations_to_db([rel], db)
        await flush_relations_to_db([rel], db)

        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT COUNT(*) FROM topic_relations").fetchone()
        assert rows[0] == 1  # only one row despite calling twice
        conn.close()
