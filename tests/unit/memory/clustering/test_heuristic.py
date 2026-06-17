"""Tests for HeuristicClusterer, Cluster, and related utilities."""
from __future__ import annotations

import json
import sqlite3
import uuid

import pytest

from src.memory.clustering.heuristic import (
    HeuristicClusterer,
    Cluster,
    jaccard_similarity,
    flush_clusters_to_db,
)
from src.memory.clustering.relations import detect_relations


# ── DB DDL for flush tests ──────────────────────────────────────────

_TOPIC_CLUSTERS_DDL = """
CREATE TABLE IF NOT EXISTS topic_clusters (
    cluster_id TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    exchange_count INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
    weight REAL NOT NULL DEFAULT 1.0
)
"""

_EXCHANGE_CLUSTERS_DDL = """
CREATE TABLE IF NOT EXISTS exchange_clusters (
    exchange_rowid INTEGER NOT NULL,
    cluster_id TEXT NOT NULL,
    similarity REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (exchange_rowid, cluster_id)
)
"""

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


# ── Jaccard similarity ──────────────────────────────────────────────

class TestJaccardSimilarity:
    def test_empty_sets(self):
        assert jaccard_similarity(set(), set()) == 0.0
        assert jaccard_similarity({"a"}, set()) == 0.0

    def test_identical_sets(self):
        assert jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    def test_no_overlap(self):
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        sim = jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        assert sim == pytest.approx(2 / 4)


# ── Cluster unit tests ──────────────────────────────────────────────

class TestCluster:
    def test_default_id_is_unique(self):
        c1 = Cluster()
        c2 = Cluster()
        assert c1.id != c2.id

    def test_custom_id(self):
        c = Cluster(cluster_id="my-custom-id")
        assert c.id == "my-custom-id"

    def test_update_adds_keywords(self):
        c = Cluster()
        c.update({"python": 1.0, "code": 0.5}, session_id="s1")
        assert c.keywords["python"] == 1.0
        assert c.keywords["code"] == 0.5
        assert c.exchange_count == 1
        assert c.session_ids == {"s1"}

    def test_update_averages_keywords(self):
        c = Cluster()
        c.update({"python": 1.0}, session_id="s1")
        c.update({"python": 0.5}, session_id="s2")
        assert c.keywords["python"] == pytest.approx(0.75)

    def test_update_tracks_multiple_sessions(self):
        c = Cluster()
        c.update({"python": 1.0}, session_id="s1")
        c.update({"python": 0.5}, session_id="s2")
        c.update({"python": 0.0}, session_id="s1")
        assert c.session_ids == {"s1", "s2"}

    def test_auto_label_from_top_keywords(self):
        c = Cluster()
        c.update({"python": 1.0, "code": 0.8, "function": 0.6, "debug": 0.1}, session_id="s1")
        assert c.label == "python, code, function"

    def test_as_dict_format(self):
        c = Cluster(cluster_id="test-as-dict")
        c.update({"python": 1.0, "code": 0.8, "function": 0.6}, session_id="s1")
        d = c.as_dict
        assert d["id"] == "test-as-dict"
        assert "python" in d["label"]
        assert isinstance(d["keywords"], list)
        assert d["keywords"][0][0] == "python"
        assert d["exchange_count"] == 1
        assert d["session_count"] == 1
        assert d["weight"] == 1.0
        assert "first_seen" in d
        assert "last_updated" in d

    def test_as_dict_keywords_sorted(self):
        c = Cluster()
        c.update({"zebra": 0.1, "alpha": 1.0, "beta": 0.9}, session_id="s1")
        d = c.as_dict
        words = [kw for kw, _ in d["keywords"]]
        assert words == ["alpha", "beta", "zebra"]

    def test_as_dict_limits_to_five_keywords(self):
        c = Cluster()
        big = {str(i): float(i) for i in range(20)}
        c.update(big, session_id="s1")
        d = c.as_dict
        assert len(d["keywords"]) == 5


# ── HeuristicClusterer ──────────────────────────────────────────────

class TestHeuristicClusterer:
    def test_empty(self):
        clusterer = HeuristicClusterer()
        assert clusterer.clusters == {}
        assert clusterer.get_all_clusters() == []
        assert clusterer.get_active_clusters() == []
        assert clusterer.get_summary() == {
            "total_clusters": 0,
            "active_clusters": 0,
            "total_exchanges": 0,
            "labels": [],
        }

    def test_single_item(self):
        clusterer = HeuristicClusterer()
        kw = {"python": 1.0, "code": 0.8}
        cluster = clusterer.assign(kw, session_id="session-1")

        assert len(clusterer.clusters) == 1
        assert cluster.id is not None
        assert cluster.exchange_count == 1
        assert cluster.session_ids == {"session-1"}
        assert clusterer.clusters[cluster.id] is cluster

    def test_similar_items_same_cluster(self):
        clusterer = HeuristicClusterer()
        kw1 = {"python": 1.0, "code": 0.8, "function": 0.6}
        kw2 = {"python": 0.9, "code": 0.7, "function": 0.5}
        kw3 = {"python": 1.0, "code": 0.9, "function": 0.7}

        c1 = clusterer.assign(kw1, session_id="s1")
        c2 = clusterer.assign(kw2, session_id="s1")
        c3 = clusterer.assign(kw3, session_id="s2")

        assert len(clusterer.clusters) == 1
        assert c1.id == c2.id == c3.id
        assert clusterer.clusters[c1.id].exchange_count == 3
        assert clusterer.clusters[c1.id].session_ids == {"s1", "s2"}

    def test_different_items_separate_clusters(self):
        clusterer = HeuristicClusterer()
        kw1 = {"python": 1.0, "code": 0.8, "function": 0.6}
        kw2 = {"cooking": 1.0, "recipe": 0.9, "food": 0.8}
        kw3 = {"soccer": 1.0, "goal": 0.7, "match": 0.6}

        c1 = clusterer.assign(kw1, session_id="s1")
        c2 = clusterer.assign(kw2, session_id="s1")
        c3 = clusterer.assign(kw3, session_id="s1")

        assert len(clusterer.clusters) == 3
        assert len({c1.id, c2.id, c3.id}) == 3

    def test_get_cluster(self):
        clusterer = HeuristicClusterer()
        c = clusterer.assign({"python": 1.0}, session_id="s1")
        assert clusterer.get_cluster(c.id) is c
        assert clusterer.get_cluster("nonexistent") is None

    def test_get_active_clusters_filters_by_min_exchanges(self):
        clusterer = HeuristicClusterer()
        clusterer.assign({"python": 1.0}, session_id="s1")  # 1 exchange
        c2 = clusterer.assign({"go": 1.0}, session_id="s1")
        clusterer.assign({"go": 0.8, "golang": 0.5}, session_id="s1")  # c2 now has 2

        # Also add a 3rd cluster with 2+ exchanges via various assigns
        c3 = clusterer.assign({"rust": 1.0}, session_id="s1")
        clusterer.assign({"rust": 0.9, "cargo": 0.5}, session_id="s1")
        clusterer.assign({"rust": 0.8}, session_id="s2")  # c3 now has 3

        active = clusterer.get_active_clusters(min_exchanges=2)
        assert len(active) >= 2
        for c in active:
            assert c.exchange_count >= 2

    def test_get_summary_with_clusters(self):
        clusterer = HeuristicClusterer()
        clusterer.assign({"python": 1.0, "code": 0.8}, session_id="s1")
        clusterer.assign({"cooking": 1.0, "recipe": 0.9}, session_id="s1")
        summary = clusterer.get_summary()
        assert summary["total_clusters"] == 2
        assert summary["active_clusters"] == 2
        assert summary["total_exchanges"] == 2
        assert len(summary["labels"]) == 2

    def test_assign_from_keyword_list(self):
        clusterer = HeuristicClusterer()
        kw_list = [("python", 1.0), ("code", 0.8)]
        c = clusterer.assign_from_keyword_list(kw_list, session_id="s1")
        assert c.exchange_count == 1
        assert "python" in c.keywords
        assert "code" in c.keywords

    def test_threshold_above_min_similarity_assigns_to_existing(self):
        """Jaccard > 0.15 → assigned to existing cluster."""
        clusterer = HeuristicClusterer()
        clusterer.assign({"a": 1.0, "b": 0.8, "c": 0.6, "d": 0.4, "e": 0.3, "f": 0.2, "g": 0.1}, session_id="s1")
        # New item: {a, b, g} ∩ existing {a..g} = {a, b, g} → Jaccard = 3/7 ≈ 0.43 > 0.15
        c = clusterer.assign({"a": 0.5, "b": 0.5, "g": 0.5}, session_id="s2")
        assert len(clusterer.clusters) == 1

    def test_threshold_below_min_similarity_creates_new(self):
        """Jaccard < 0.15 → new cluster."""
        clusterer = HeuristicClusterer()
        clusterer.assign({"a": 1.0, "b": 0.8, "c": 0.6, "d": 0.4, "e": 0.3, "f": 0.2, "g": 0.1}, session_id="s1")
        # New item: {a, x, y} ∩ existing {a..g} = {a} → Jaccard = 1/9 ≈ 0.11 < 0.15
        c = clusterer.assign({"a": 0.5, "x": 0.5, "y": 0.5}, session_id="s2")
        assert len(clusterer.clusters) == 2
        assert c.id != list(clusterer.clusters.values())[0].id


# ── Merge behavior ──────────────────────────────────────────────────

class TestMerge:
    def test_merge_similar_above_threshold(self):
        """_merge_similar merges clusters with Jaccard >= 0.35."""
        clusterer = HeuristicClusterer()

        c1 = Cluster()
        c1.update({"a": 1.0, "b": 0.8, "c": 0.6}, session_id="s1")
        clusterer.clusters[c1.id] = c1

        c2 = Cluster()
        c2.update({"b": 0.9, "c": 0.7, "d": 0.5}, session_id="s1")
        c2.update({"b": 0.8, "c": 0.6, "d": 0.4, "e": 0.3}, session_id="s2")
        clusterer.clusters[c2.id] = c2

        # Jaccard({a,b,c}, {b,c,d,e}) = {b,c}/{a,b,c,d,e} = 2/5 = 0.4 >= 0.35
        merged = clusterer._merge_similar()
        assert merged == 1
        assert len(clusterer.clusters) == 1

    def test_merge_preserves_cluster_with_more_exchanges(self):
        """When merging, the cluster with more exchanges survives."""
        clusterer = HeuristicClusterer()

        c_keep = Cluster()
        c_keep.update({"a": 0.1, "b": 0.9, "c": 0.8, "d": 0.7}, session_id="s1")
        c_keep.update({"a": 0.2, "b": 0.8, "c": 0.9, "d": 0.6}, session_id="s2")
        c_keep.update({"a": 0.1, "b": 1.0, "c": 0.7, "d": 0.8}, session_id="s3")
        kept_id = c_keep.id
        clusterer.clusters[kept_id] = c_keep

        c_remove = Cluster()
        c_remove.update({"b": 0.8, "c": 0.7, "e": 0.5}, session_id="s1")
        removed_id = c_remove.id
        clusterer.clusters[removed_id] = c_remove

        # Jaccard({a,b,c,d}, {b,c,e}) = {b,c}/{a,b,c,d,e} = 2/5 = 0.4 >= 0.35
        clusterer._merge_similar()

        assert kept_id in clusterer.clusters
        assert removed_id not in clusterer.clusters
        assert clusterer.clusters[kept_id].exchange_count >= 4  # 3 + 1 (at least)

    def test_no_merge_below_threshold(self):
        """Clusters with Jaccard < 0.35 are not merged."""
        clusterer = HeuristicClusterer()

        c1 = Cluster()
        c1.update({"a": 1.0, "b": 1.0}, session_id="s1")
        clusterer.clusters[c1.id] = c1

        c2 = Cluster()
        c2.update({"c": 1.0, "d": 1.0, "e": 1.0}, session_id="s1")
        clusterer.clusters[c2.id] = c2

        # Jaccard({a,b}, {c,d,e}) = {}/{a,b,c,d,e} = 0/5 = 0.0 < 0.35
        merged = clusterer._merge_similar()
        assert merged == 0
        assert len(clusterer.clusters) == 2

    def test_merge_updates_keywords_correctly(self):
        """After merge, centroid keywords reflect weighted average."""
        clusterer = HeuristicClusterer()

        c1 = Cluster()
        c1.update({"a": 1.0, "b": 0.5}, session_id="s1")
        c1.update({"a": 0.5, "b": 1.0}, session_id="s2")
        clusterer.clusters[c1.id] = c1

        c2 = Cluster()
        c2.update({"a": 0.0, "b": 0.0}, session_id="s3")
        clusterer.clusters[c2.id] = c2

        # Jaccard({a,b}, {a,b}) = 1.0 >= 0.35
        clusterer._merge_similar()

        remaining = list(clusterer.clusters.values())[0]
        # c1 had 2 exchanges, c2 had 1.
        # a: (0.75*2 + 0.0*1) / 3 = 1.5/3 = 0.5
        # b: (0.75*2 + 0.0*1) / 3 = 1.5/3 = 0.5
        assert remaining.keywords["a"] == pytest.approx(0.5)
        assert remaining.keywords["b"] == pytest.approx(0.5)
        assert remaining.exchange_count == 3


# ── DB flush ────────────────────────────────────────────────────────

class TestFlushClustersToDB:
    def _create_schema(self, conn: sqlite3.Connection):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(_TOPIC_CLUSTERS_DDL)
        conn.execute(_EXCHANGE_CLUSTERS_DDL)
        conn.commit()

    @pytest.mark.asyncio
    async def test_flush_empty_clusterer(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        clusterer = HeuristicClusterer()
        count = await flush_clusters_to_db(clusterer, db)
        assert count == 0

        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT COUNT(*) FROM topic_clusters").fetchone()
        assert rows[0] == 0
        conn.close()

    @pytest.mark.asyncio
    async def test_flush_writes_clusters(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        clusterer = HeuristicClusterer()
        clusterer.assign({"python": 1.0, "code": 0.8}, session_id="s1")
        clusterer.assign({"cooking": 1.0, "recipe": 0.9}, session_id="s1")

        count = await flush_clusters_to_db(clusterer, db)
        assert count == 2

        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT cluster_id, label, exchange_count, session_count FROM topic_clusters").fetchall()
        assert len(rows) == 2
        for cid, label, ec, sc in rows:
            assert label
            assert ec == 1
            assert sc == 1
        conn.close()

    @pytest.mark.asyncio
    async def test_flush_with_mappings(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        clusterer = HeuristicClusterer()
        c = clusterer.assign({"python": 1.0}, session_id="s1")

        mappings = [{"exchange_rowid": 42, "cluster_id": c.id, "similarity": 0.95}]
        count = await flush_clusters_to_db(clusterer, db, mappings=mappings)
        assert count == 1

        conn = sqlite3.connect(db)
        ex_rows = conn.execute("SELECT exchange_rowid, cluster_id, similarity FROM exchange_clusters").fetchall()
        assert len(ex_rows) == 1
        assert ex_rows[0][0] == 42
        assert ex_rows[0][1] == c.id
        assert ex_rows[0][2] == pytest.approx(0.95)
        conn.close()

    @pytest.mark.asyncio
    async def test_flush_updates_existing_cluster(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        clusterer = HeuristicClusterer()
        c = clusterer.assign({"python": 1.0}, session_id="s1")

        await flush_clusters_to_db(clusterer, db)

        clusterer.assign({"python": 0.8, "code": 0.6}, session_id="s2")
        count = await flush_clusters_to_db(clusterer, db)
        assert count == 0  # UPDATE doesn't increment count

        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT exchange_count, session_count FROM topic_clusters WHERE cluster_id = ?",
            (c.id,)
        ).fetchone()
        assert row[0] == 2
        assert row[1] == 2
        conn.close()

    @pytest.mark.asyncio
    async def test_flush_keywords_json_format(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        self._create_schema(conn)
        conn.close()

        clusterer = HeuristicClusterer()
        clusterer.assign({"python": 1.0, "code": 0.8, "function": 0.6}, session_id="s1")
        await flush_clusters_to_db(clusterer, db)

        conn = sqlite3.connect(db)
        row = conn.execute("SELECT keywords FROM topic_clusters").fetchone()
        keywords = json.loads(row[0])
        assert isinstance(keywords, list)
        assert keywords[0]["word"] == "python"
        assert keywords[0]["score"] == 1.0
        conn.close()


# ── Detect relations (integration with heuristic output) ────────────

class TestDetectRelationsWithHeuristic:
    def test_empty_clusters(self):
        assert detect_relations([]) == []

    def test_single_cluster_no_relations(self):
        clusters = [
            {"id": "c1", "keywords": [("python", 1.0), ("code", 0.8)]},
        ]
        assert detect_relations(clusters) == []

    def test_clusters_with_shared_keywords(self):
        clusters = [
            {"id": "c1", "keywords": [("python", 1.0), ("code", 0.8), ("function", 0.6)]},
            {"id": "c2", "keywords": [("python", 0.5), ("code", 0.4), ("cooking", 1.0)]},
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 1
        ids = {rels[0]["source_id"], rels[0]["target_id"]}
        assert ids == {"c1", "c2"}
        assert set(rels[0]["shared_keywords"]) == {"python", "code"}
        assert rels[0]["shared_count"] == 2

    def test_no_relation_below_min_shared(self):
        clusters = [
            {"id": "c1", "keywords": [("python", 1.0)]},
            {"id": "c2", "keywords": [("python", 0.5), ("cooking", 1.0)]},
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 0

    def test_strong_relation(self):
        clusters = [
            {"id": "c1", "keywords": [("a", 1.0), ("b", 0.8), ("c", 0.6), ("d", 0.4)]},
            {"id": "c2", "keywords": [("a", 0.5), ("b", 0.4), ("c", 0.3), ("d", 0.2), ("e", 1.0)]},
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 1
        assert rels[0]["shared_count"] == 4
        assert rels[0]["relationship_type"] == "strongly_related"

    def test_relation_weight_is_jaccard(self):
        clusters = [
            {"id": "c1", "keywords": [("a", 1.0), ("b", 0.8), ("c", 0.6), ("d", 0.4)]},
            {"id": "c2", "keywords": [("a", 0.5), ("b", 0.4), ("c", 0.3), ("x", 1.0), ("y", 0.5)]},
        ]
        rels = detect_relations(clusters)
        assert len(rels) == 1
        shared = {"a", "b", "c"}
        union = {"a", "b", "c", "d", "x", "y"}
        expected_weight = len(shared) / len(union)
        assert rels[0]["weight"] == pytest.approx(expected_weight)
