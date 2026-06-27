"""Embedding service using fastembed (sentence-transformers via ONNX).

The active embedding model lives as a module-level singleton so that all
threads and asyncio contexts share the same loaded model.  The model is
thread-safe (RLock inside EmbeddingService) and loads lazily on the first
call, then stays resident for the life of the process.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


class EmbeddingService:
    """Lazy embedding loader with explicit lifecycle control."""

    def __init__(self, model: Optional[TextEmbedding] = None) -> None:
        self._lock = threading.RLock()
        self._model = model
        self._last_used = time.time() if model is not None else 0.0

    def configure_model(self, model: Optional[TextEmbedding]) -> None:
        """Set the active embedding model explicitly, or clear it with None."""
        with self._lock:
            self._model = model
            self._last_used = time.time() if model is not None else 0.0

    def get_model(self) -> Optional[TextEmbedding]:
        """Get or initialize the embedding model.

        Returns None if the model failed to load (e.g. no network, disk full,
        corrupted cache). Callers MUST handle None gracefully.
        """
        with self._lock:
            if self._model is None:
                logger.info("Loading embedding model: %s", DEFAULT_MODEL)
                try:
                    self._model = TextEmbedding(model_name=DEFAULT_MODEL)
                    logger.info("Embedding model loaded successfully")
                except Exception as exc:
                    logger.error(
                        "Failed to load embedding model '%s': %s. "
                        "Semantic search will be degraded (keyword+entity only). "
                        "Check internet connection or model cache.",
                        DEFAULT_MODEL,
                        exc,
                    )
                    return None
            self._last_used = time.time()
            return self._model

    def generate_embedding(self, text: str) -> list[float]:
        """Generate a single embedding vector for the given text."""
        model = self.get_model()
        if model is None:
            logger.warning("Embedding model not available, returning zero vector")
            return [0.0] * EMBEDDING_DIM
        vectors = list(model.embed([text]))
        if not vectors:
            logger.warning("Empty embedding returned for text")
            return [0.0] * EMBEDDING_DIM
        return vectors[0].tolist()

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        model = self.get_model()
        if model is None:
            logger.warning(
                "Embedding model not available, returning zero vectors for batch"
            )
            return [[0.0] * EMBEDDING_DIM for _ in texts]
        vectors = list(model.embed(texts))
        return [v.tolist() for v in vectors]

    def unload_if_idle(self, force: bool = False) -> bool:
        """Unload the embedding model if idle timeout elapsed."""
        with self._lock:
            if self._model is None:
                return False
            if force or (time.time() - self._last_used > IDLE_TIMEOUT):
                self._model = None
                self._last_used = 0.0
                logger.info("Embedding model unloaded")
                return True
            return False

    def unload_model(self) -> None:
        """Unload the model to free memory (useful for maintenance)."""
        with self._lock:
            if self._model is not None:
                self._model = None
                self._last_used = 0.0
                logger.info("Embedding model unloaded")


IDLE_TIMEOUT: float = 999999.0  # Nunca descargar de RAM

_service: EmbeddingService | None = None
_service_lock: threading.Lock = threading.Lock()


def get_service() -> EmbeddingService:
    """Get or create the shared embedding service (module-level singleton).

    The EmbeddingService is thread-safe (uses RLock internally), so a single
    instance can be shared safely across all threads and asyncio contexts.
    This avoids reloading the ONNX model on every call, which was the previous
    behaviour with per-context ContextVar (each thread call loaded the model
    from disk again).
    """
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = EmbeddingService()
    return _service


def configure_model(model: Optional[TextEmbedding]) -> None:
    """Set the active embedding model explicitly, or clear it with None."""
    get_service().configure_model(model)


def reset_model() -> None:
    """Replace the shared service with a fresh lazy instance."""
    global _service
    _service = EmbeddingService()

def get_model() -> Optional[TextEmbedding]:
    """Get or initialize the embedding model through the active service."""
    return get_service().get_model()


def generate_embedding(text: str) -> list[float]:
    """Generate a single embedding vector for the given text."""
    return get_service().generate_embedding(text)


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    return get_service().generate_embeddings_batch(texts)


def unload_if_idle(force: bool = False) -> bool:
    """Unload the embedding model if idle timeout elapsed."""
    return get_service().unload_if_idle(force=force)


def unload_model() -> None:
    """Unload the model to free memory (useful for maintenance)."""
    get_service().unload_model()
