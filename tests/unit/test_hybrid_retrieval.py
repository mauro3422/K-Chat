"""Tests for the hybrid retrieval pipeline: fusion, keyword, entity, and relevance."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.memory.retrieval.fusion import (
    FusionConfig,
    fuse,
    fuse_rrf,
    fuse_weighted_sum,
    normalize_scores,
)
from src.memory.vector.store import compute_relevance


class TestFusionRRF:
    def test_fuse_rrf_empty(self):
        assert fuse_rrf([], k=60) == []

    def test_fuse_rrf_single_list(self):
        result = fuse_rrf([[10, 20, 30]], k=60)
        assert len(result) == 3
        scores = dict(result)
        assert scores[10] > scores[20] > scores[30]

    def test_fuse_rrf_multi_list(self):
        result = fuse_rrf([[10, 20], [20, 10], [10, 30]], k=60)
        scores = dict(result)
        assert scores[10] > 0
        assert scores[20] > 0
        assert scores[10] > scores[30]
        assert scores[20] > scores[30]

    def test_fuse_rrf_min_score(self):
        """Results with score >= FusionConfig.min_score pass through."""
        result = fuse_rrf([[10, 20, 30]], k=60)
        config = FusionConfig(method="rrf")
        filtered = [(rid, s) for rid, s in result if s >= config.min_score]
        assert len(filtered) > 0

    def test_fuse_rrf_min_score_excludes_below(self):
        """Items with RRF score below min_score are excluded from results."""
        ranked_lists = [
            [10, 20, 30],
            [10, 40],
            [10, 50],
        ]
        config = FusionConfig(method="rrf", min_score=0.02)
        result = fuse(ranked_lists, config=config)
        rowids = {rid for rid, _ in result}
        assert 10 in rowids       # 3/61 ≈ 0.049 >= 0.02
        assert 20 not in rowids   # 1/62 ≈ 0.016 < 0.02
        assert 30 not in rowids   # 1/63 ≈ 0.016 < 0.02
        assert 40 not in rowids   # 1/62 ≈ 0.016 < 0.02
        assert 50 not in rowids   # 1/62 ≈ 0.016 < 0.02


class TestFusionWeightedSum:
    def test_fuse_weighted_sum(self):
        scored = [
            [(10, 1.0), (20, 0.5)],
            [(20, 1.0), (10, 0.3)],
            [(10, 0.8), (30, 0.6)],
        ]
        result = fuse_weighted_sum(scored, (0.4, 0.3, 0.3))
        scores = dict(result)
        assert abs(scores[10] - 0.73) < 0.01
        assert abs(scores[20] - 0.50) < 0.01

    def test_fuse_weighted_sum_empty(self):
        assert fuse_weighted_sum([[(1, 0.5)]], (1.0,)) == [(1, 0.5)]

    def test_fuse_weighted_sum_fewer_signals(self):
        result = fuse_weighted_sum([[(1, 1.0)]], (0.5, 0.5))
        assert result == [(1, 0.5)]

    def test_fuse_weighted_sum_min_score(self):
        """Weighted sum fusion excludes items below min_score."""
        scored = [
            [(10, 1.0), (20, 0.1)],
            [(10, 0.8)],
            [(10, 0.6)],
        ]
        config = FusionConfig(
            method="weighted_sum", weights=(0.4, 0.3, 0.3), min_score=0.05
        )
        result = fuse(ranked_lists=[], scored_lists=scored, config=config)
        rowids = {rid for rid, _ in result}
        assert 10 in rowids       # 0.4 + 0.24 + 0.18 = 0.82 >= 0.05
        assert 20 not in rowids   # 0.1 * 0.4 = 0.04 < 0.05


class TestNormalizeScores:
    def test_normalize_scores_empty(self):
        assert normalize_scores([]) == []

    def test_normalize_scores_single(self):
        assert normalize_scores([(1, 5.0)]) == [(1, 5.0)]

    def test_normalize_scores_all_equal(self):
        assert normalize_scores([(1, 0.5), (2, 0.5)]) == [(1, 0.5), (2, 0.5)]

    def test_normalize_scores_varied(self):
        result = normalize_scores([(1, 1.0), (2, 5.0), (3, 3.0)])
        scores = dict(result)
        assert abs(scores[1] - 0.0) < 0.001
        assert abs(scores[2] - 1.0) < 0.001
        assert abs(scores[3] - 0.5) < 0.001


class TestFuse:
    def test_fuse_fallback(self):
        """fuse() with weighted_sum but no scored_lists falls back to RRF."""
        result = fuse(
            [[1, 2], [2, 1]],
            scored_lists=None,
            config=FusionConfig(method="weighted_sum"),
        )
        assert len(result) > 0
        scores = dict(result)
        assert scores[2] > 0

    def test_fuse_rrf_default(self):
        result = fuse([[1, 2], [2, 1]], config=FusionConfig(method="rrf"))
        assert len(result) > 0

    def test_fuse_unknown_method(self):
        with pytest.raises(ValueError, match="Unknown fusion method"):
            fuse([], config=FusionConfig(method="unknown"))

    def test_fuse_min_score_zero(self):
        """min_score=0.0 includes all items regardless of score."""
        result = fuse([[10, 20]], config=FusionConfig(method="rrf", min_score=0.0))
        assert len(result) == 2

    def test_fuse_min_score_one(self):
        """min_score=1.0 excludes everything (max RRF score is ~0.049)."""
        result = fuse(
            [[10, 20], [10], [10]],
            config=FusionConfig(method="rrf", min_score=1.0),
        )
        assert result == []


class TestComputeRelevance:
    def test_compute_relevance_defaults(self):
        score = compute_relevance()
        assert 0.0 <= score <= 1.0

    def test_compute_relevance_memory_boost(self):
        mem = compute_relevance(source="memory")
        sess = compute_relevance(source="session")
        assert mem > sess

    def test_compute_relevance_full_signals(self):
        score = compute_relevance(
            avg_tfidf=0.8,
            entity_count=20,
            cluster_weight=1.0,
            days_old=1.0,
            source="memory",
        )
        assert 0.0 <= score <= 1.0
        assert score > compute_relevance()

    def test_compute_relevance_bounds(self):
        score = compute_relevance(
            avg_tfidf=-1.0, entity_count=1000, days_old=-5.0
        )
        assert 0.0 <= score <= 1.0

    def test_compute_relevance_old_data(self):
        old = compute_relevance(days_old=365.0)
        recent = compute_relevance(days_old=1.0)
        assert old < recent


class TestKeywordSearch:
    @patch("src.memory.keywords.extractor.extract_keywords")
    @patch("src.memory.retrieval.keyword_search.sqlite3.connect")
    def test_keyword_search_empty_query(self, mock_connect, mock_extract):
        mock_extract.return_value = []
        from src.memory.retrieval.keyword_search import keyword_search

        result = keyword_search("", "/fake/path")
        assert result == []
        mock_connect.assert_not_called()

    @patch("src.memory.keywords.extractor.extract_keywords")
    @patch("src.memory.retrieval.keyword_search.sqlite3.connect")
    def test_keyword_search_finds_results(self, mock_connect, mock_extract):
        mock_extract.return_value = [("python", 0.8), ("async", 0.5)]
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [(1, 1.5), (2, 0.8)]
        from src.memory.retrieval.keyword_search import keyword_search

        result = keyword_search("python async", "/fake/path")
        assert result == [(1, 1.5), (2, 0.8)]
        mock_conn.close.assert_called_once()

    @patch("src.memory.keywords.extractor.extract_keywords")
    @patch("src.memory.retrieval.keyword_search.sqlite3.connect")
    def test_keyword_search_with_source_filter(self, mock_connect, mock_extract):
        mock_extract.return_value = [("python", 0.8)]
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [(1, 1.5)]
        from src.memory.retrieval.keyword_search import keyword_search

        result = keyword_search("python", "/fake/path", source_filter="memory")
        assert result == [(1, 1.5)]
        call_args = mock_conn.execute.call_args[0][0]
        assert "m.source = ?" in call_args


class TestEntitySearch:
    @patch("src.memory.entity.extractor.extract_entities")
    @patch("src.memory.retrieval.entity_search.sqlite3.connect")
    def test_entity_search_empty(self, mock_connect, mock_extract):
        mock_extract.return_value = []
        from src.memory.retrieval.entity_search import entity_search

        result = entity_search("", "/fake/path")
        assert result == []
        mock_connect.assert_called_once_with("/fake/path")

    @patch("src.memory.entity.extractor.extract_entities")
    @patch("src.memory.retrieval.entity_search.sqlite3.connect")
    def test_entity_search_finds_results(self, mock_connect, mock_extract):
        mock_extract.return_value = [("persona", "Mauro", None)]
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [(1, 5.0)]
        from src.memory.retrieval.entity_search import entity_search

        result = entity_search("habla sobre Mauro", "/fake/path")
        assert result == [(1, 10.0)]
        mock_conn.close.assert_called_once()

    @patch("src.memory.entity.extractor.extract_entities")
    @patch("src.memory.retrieval.entity_search.sqlite3.connect")
    def test_entity_search_with_source_filter(self, mock_connect, mock_extract):
        mock_extract.return_value = [("tecnologia", "Python", None)]
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [(1, 2.0)]
        from src.memory.retrieval.entity_search import entity_search

        result = entity_search("Python", "/fake/path", source_filter="session")
        assert result == [(1, 4.0)]
        call_args = mock_conn.execute.call_args_list[0][0][0]
        assert "m.source = ?" in call_args


class TestHybridRetrieverMinScore:
    @pytest.mark.asyncio
    async def test_hybrid_retriever_double_min_score_filter(self, tmp_path):
        """Redundant min_score filter in hybrid_retriever.search() is harmless.

        fuse() already filters by min_score, and the redundant filter on line 121
        doesn't remove any additional items.
        """
        import sqlite3

        from src.memory.retrieval.hybrid_retriever import HybridRetriever

        db_path = str(tmp_path / "test_memory.db")

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE vec_meta (
                rowid INTEGER PRIMARY KEY,
                source TEXT,
                source_key TEXT,
                text TEXT,
                relevance_score REAL,
                query_count INTEGER,
                last_accessed TEXT
            )
        """)
        for rowid in range(1, 7):
            conn.execute(
                "INSERT INTO vec_meta (rowid, source, source_key, text, relevance_score, query_count, last_accessed) VALUES (?, 'memory', ?, ?, 0.5, 0, '')",
                (rowid, f"key{rowid}", f"text {rowid}"),
            )
        conn.commit()
        conn.close()

        config = FusionConfig(method="rrf", min_score=0.03)
        retriever = HybridRetriever(db_path=db_path, fusion_config=config)

        vec_results = [(1, 1.0), (2, 0.9), (3, 0.8)]
        kw_results = [(2, 1.0), (4, 0.9), (1, 0.8)]
        ent_results = [(3, 1.0), (5, 0.9), (1, 0.8)]

        with (
            patch.object(retriever, "_vector_search", return_value=vec_results),
            patch(
                "src.memory.retrieval.hybrid_retriever.keyword_search",
                return_value=kw_results,
            ),
            patch(
                "src.memory.retrieval.hybrid_retriever.entity_search",
                return_value=ent_results,
            ),
        ):
            results = await retriever.search("test query", top_k=10)

        result_rowids = {r.rowid for r in results}

        # RRF scores:
        #   1: 3/61 ≈ 0.049 (>=0.03 ✓)
        #   2: 1/62 + 1/61 ≈ 0.032 (>=0.03 ✓)
        #   3: 1/63 + 1/61 ≈ 0.032 (>=0.03 ✓)
        #   4: 1/62 ≈ 0.016 (<0.03 ✗)
        #   5: 1/62 ≈ 0.016 (<0.03 ✗)
        assert 1 in result_rowids
        assert 2 in result_rowids
        assert 3 in result_rowids
        assert 4 not in result_rowids
        assert 5 not in result_rowids
