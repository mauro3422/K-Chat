"""Cross-encoder reranker for memory retrieval.

The active reranker is kept on a context-local service instance so callers can
inject a specific model without a process-wide singleton.
"""

from __future__ import annotations

from contextvars import ContextVar
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder reranker with lazy-loaded model."""

    def __init__(self):
        self._lock = threading.RLock()
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
        """Re-rank candidates by cross-encoder relevance to query."""
        with self._lock:
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
        with self._lock:
            if self._model is not None:
                self._model = None
                self._ready = False
                logger.info("Cross-encoder model unloaded")


_current_reranker: ContextVar[Reranker | None] = ContextVar(
    "kairos_reranker",
    default=None,
)


def get_reranker() -> Reranker:
    """Get the context-local reranker instance."""
    reranker = _current_reranker.get()
    if reranker is None:
        reranker = Reranker()
        _current_reranker.set(reranker)
    return reranker


def configure_reranker(reranker: Reranker | None) -> None:
    """Set the active reranker explicitly, or clear it with None."""
    if reranker is None:
        reset_reranker()
        return
    _current_reranker.set(reranker)


def reset_reranker() -> None:
    """Replace the current context reranker with a fresh lazy instance."""
    _current_reranker.set(Reranker())


def rerank(
    query: str, candidates: list[dict[str, Any]], top_k: int = 8
) -> list[dict[str, Any]]:
    """Re-rank candidates using the active Reranker instance."""
    return get_reranker().rerank(query, candidates, top_k)


def unload_model():
    """Unload the active reranker instance to free memory."""
    get_reranker().unload()
