"""Tests for RRF fusion and scoring."""

from __future__ import annotations

import pytest

from src.memory.retrieval.fusion import (
    fuse_rrf,
    fuse_weighted_sum,
    normalize_scores,
)


class TestRRFFusion:
    def test_empty_inputs(self):
        assert fuse_rrf([]) == []
        assert fuse_rrf([[], []]) == []

    def test_single_list(self):
        results = fuse_rrf([
            [1, 2, 3],
        ], k=60)
        assert len(results) == 3
        assert results[0][0] == 1

    def test_two_lists_boosts_common(self):
        results = fuse_rrf([
            [1, 2],
            [1, 3],
        ], k=60)
        ids = [r[0] for r in results]
        assert ids[0] == 1

    def test_score_range(self):
        results = fuse_rrf([
            [1, 2],
            [3, 4],
        ], k=60)
        for _, score in results:
            assert 0 <= score <= 1.0


class TestWeightedSum:
    def test_empty(self):
        assert fuse_weighted_sum([], (0.4, 0.3, 0.3)) == []

    def test_basic_weighted(self):
        results = fuse_weighted_sum([
            [(1, 1.0), (2, 0.5)],
            [(1, 0.5), (3, 1.0)],
        ], weights=(0.7, 0.3, 0.0))
        result_dict = dict(results)
        assert result_dict[1] == pytest.approx(0.85)
        assert result_dict[2] == pytest.approx(0.35)
        assert result_dict[3] == pytest.approx(0.30)


class TestNormalizeScores:
    def test_empty(self):
        assert normalize_scores([]) == []

    def test_normalize(self):
        scores = [(1, 10.0), (2, 5.0), (3, 0.0)]
        normalized = normalize_scores(scores)
        assert normalized[0][1] == pytest.approx(1.0)
        assert normalized[1][1] == pytest.approx(0.5)
        assert normalized[2][1] == pytest.approx(0.0)

    def test_all_same_score(self):
        scores = [(1, 5.0), (2, 5.0)]
        normalized = normalize_scores(scores)
        assert normalized[0][1] == pytest.approx(5.0)
        assert normalized[1][1] == pytest.approx(5.0)
