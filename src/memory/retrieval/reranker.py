"""Cross-encoder reranker for memory retrieval.

Takes a query + candidate texts and re-ranks them using a BERT cross-encoder
via fastembed (ONNX runtime, no PyTorch needed).

Model: Xenova/ms-marco-MiniLM-L-6-v2
"""

from __future__ import annotations
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Module-level lock for thread safety
_reranker_lock = threading.Lock()


class Reranker:
    """Cross-encoder reranker with lazy-loaded model.

    The model is NOT loaded at construction time — it is loaded on the first
    call to rerank(). If loading fails, rerank() returns candidates unchanged.
    """

    def __init__(self):
        self._model = None
        self._ready = False

    def _load_model(self):
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            logger.info("Loading cross-encoder model: Xenova/ms-marco-MiniLM-L-6-v2")
            self._model = TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")
            logger.info("Cross-encoder model loaded successfully")
            self._ready = True
        except Exception as e:
            logger.warning("[Notification] Reranker unavailable: %s", e)
            raise

    def rerank(
        self, query: str, candidates: list[dict[str, Any]], top_k: int = 8
    ) -> list[dict[str, Any]]:
        """Re-rank candidates by cross-encoder relevance to query.

        Args:
            query: The user's query string.
            candidates: List of dicts with at least {'text': str, 'score': float, 'rowid': int}.
            top_k: Number of results to return after re-ranking.

        Returns:
            Re-ranked candidates with updated 'score' from cross-encoder.
            Falls back to original order if model is unavailable.
        """
        if not self._ready:
            try:
                self._load_model()
            except Exception:
                return candidates[:top_k]

        if not candidates:
            return candidates[:top_k]

        texts = [c.get("text", "") for c in candidates]
        pairs = [(query, t[:512]) for t in texts]

        try:
            scores = list(self._model.rerank_pairs(pairs))
        except Exception as e:
            logger.warning("Cross-encoder predict failed: %s. Using original scores.", e)
            return candidates[:top_k]

        for i, c in enumerate(candidates):
            raw_score = float(scores[i])
            normalized = 1.0 / (1.0 + (2.71828 ** (-raw_score)))
            c["score"] = round(normalized, 4)
            c["reranker_score"] = round(normalized, 4)

        reranked = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
        return reranked[:top_k]

    def unload(self):
        """Unload model to free memory."""
        if self._model is not None:
            del self._model
            self._model = None
            self._ready = False
            logger.info("Cross-encoder model unloaded")


# Module-level singleton for backward compatibility
_reranker_instance: Reranker | None = None


def rerank(
    query: str, candidates: list[dict[str, Any]], top_k: int = 8
) -> list[dict[str, Any]]:
    """Re-rank candidates using the singleton Reranker instance."""
    global _reranker_instance
    with _reranker_lock:
        if _reranker_instance is None:
            _reranker_instance = Reranker()
        return _reranker_instance.rerank(query, candidates, top_k)


def unload_model():
    """Unload singleton instance to free memory."""
    global _reranker_instance
    with _reranker_lock:
        if _reranker_instance is not None:
            _reranker_instance.unload()
            _reranker_instance = None
