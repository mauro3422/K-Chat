"""Tests for the cross-encoder reranker module."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.memory.retrieval.reranker import (
    Reranker,
    configure_reranker,
    reset_reranker,
    rerank,
    unload_model,
)


class TestReranker:
    """Unit tests for the Reranker class."""

    def test_load_model_success(self):
        with patch("fastembed.rerank.cross_encoder.TextCrossEncoder") as mock_cls:
            mock_cls.return_value = MagicMock()
            reranker = Reranker()
            assert not reranker._ready
            assert reranker._model is None

            reranker._load_model()

            assert reranker._ready
            assert reranker._model is mock_cls.return_value

    def test_load_model_failure(self):
        with patch(
            "fastembed.rerank.cross_encoder.TextCrossEncoder",
            side_effect=OSError("model file not found"),
        ):
            reranker = Reranker()
            with pytest.raises(OSError):
                reranker._load_model()
            assert not reranker._ready

    def test_rerank_fallback_when_model_not_loaded(self):
        reranker = Reranker()
        candidates = [{"text": "a", "score": 0.5, "rowid": 1}]

        with patch.object(reranker, "_load_model", side_effect=Exception("fail")):
            result = reranker.rerank("query", candidates, top_k=8)

        assert result == candidates[:8]

    def test_rerank_empty_candidates_returns_empty(self):
        reranker = Reranker()
        reranker._ready = True
        reranker._model = MagicMock()
        result = reranker.rerank("query", [])
        assert result == []

    def test_rerank_sorts_and_returns_top_k(self):
        mock_model = MagicMock()
        mock_model.rerank_pairs.return_value = [0.5, 2.5, 1.5]

        reranker = Reranker()
        reranker._ready = True
        reranker._model = mock_model

        candidates = [
            {"text": "low", "score": 0.1, "rowid": 1},
            {"text": "high", "score": 0.2, "rowid": 2},
            {"text": "mid", "score": 0.3, "rowid": 3},
        ]

        result = reranker.rerank("query", candidates, top_k=2)

        assert len(result) == 2
        scores = [c["score"] for c in result]
        assert scores == sorted(scores, reverse=True)

    def test_rerank_propagates_prediction_error(self):
        mock_model = MagicMock()
        mock_model.rerank_pairs.side_effect = ValueError("predict failed")

        reranker = Reranker()
        reranker._ready = True
        reranker._model = mock_model

        candidates = [{"text": "hello", "score": 0.5, "rowid": 1}]
        result = reranker.rerank("query", candidates, top_k=8)
        assert result == candidates[:8]

    def test_unload_clears_model(self):
        reranker = Reranker()
        reranker._model = MagicMock()
        reranker._ready = True

        reranker.unload()

        assert reranker._model is None
        assert not reranker._ready


class TestModuleLevelFunctions:
    """Tests for module-level rerank() and unload_model()."""

    def test_rerank_empty_candidates(self):
        with patch("src.memory.retrieval.reranker._reranker_instance", None), \
             patch("src.memory.retrieval.reranker.Reranker") as mock_rr_cls:
            mock_instance = MagicMock()
            mock_instance.rerank.return_value = []
            mock_rr_cls.return_value = mock_instance

            result = rerank("query", [], top_k=8)

            assert result == []

    def test_unload_model_does_not_raise(self):
        with patch("src.memory.retrieval.reranker._reranker_instance", None):
            unload_model()

    def test_reset_reranker_restores_lazy_instance(self):
        reranker = Reranker()
        configure_reranker(reranker)
        try:
            assert rerank.__globals__["_reranker_instance"] is reranker
        finally:
            reset_reranker()
        assert rerank.__globals__["_reranker_instance"] is None
