"""Embedding service using fastembed (sentence-transformers via ONNX).

Loads a multilingual model once (singleton via module-level cache) and
generates 384-dimension embeddings for any text. Unloads after idle
timeout to free ~80MB RAM.
"""

from __future__ import annotations
from typing import Optional
import logging
import threading
import time
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

# Module-level lock for thread safety
_embedding_lock = threading.Lock()

# Module-level singleton: once loaded, it stays in memory
_embedding_model: Optional[TextEmbedding] = None

# Idle tracking: timestamp of last embedding call
_last_used: float = 0.0
IDLE_TIMEOUT: float = 300.0  # 5 minutes

# Default model: multilingual, 384 dims, ~80MB RAM
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


def get_model() -> Optional[TextEmbedding]:
    """Get or initialize the embedding model singleton.
    
    Returns None if the model failed to load (e.g. no network, disk full,
    corrupted cache). Callers MUST handle None gracefully.
    """
    global _embedding_model, _last_used
    with _embedding_lock:
        if _embedding_model is None:
            logger.info(f"Loading embedding model: {DEFAULT_MODEL}")
            try:
                _embedding_model = TextEmbedding(model_name=DEFAULT_MODEL)
                logger.info("Embedding model loaded successfully")
            except Exception as e:
                logger.error(
                    "Failed to load embedding model '%s': %s. "
                    "Semantic search will be degraded (keyword+entity only). "
                    "Check internet connection or model cache.",
                    DEFAULT_MODEL, e,
                )
                return None
        _last_used = time.time()
        return _embedding_model


def generate_embedding(text: str) -> list[float]:
    """Generate a single embedding vector for the given text.

    Args:
        text: Input text to embed.

    Returns:
        List of floats of length EMBEDDING_DIM. Returns a zero vector
        if the model is unavailable (degraded mode).
    """
    model = get_model()
    if model is None:
        logger.warning("Embedding model not available, returning zero vector")
        return [0.0] * EMBEDDING_DIM
    vectors = list(model.embed([text]))
    if not vectors:
        logger.warning("Empty embedding returned for text")
        return [0.0] * EMBEDDING_DIM
    return vectors[0].tolist()


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Args:
        texts: List of input texts.

    Returns:
        List of embedding vectors. Returns zero vectors for all texts
        if the model is unavailable (degraded mode).
    """
    model = get_model()
    if model is None:
        logger.warning("Embedding model not available, returning zero vectors for batch")
        return [[0.0] * EMBEDDING_DIM for _ in texts]
    vectors = list(model.embed(texts))
    return [v.tolist() for v in vectors]


def unload_if_idle(force: bool = False) -> bool:
    """Unload the embedding model if idle timeout elapsed.
    Returns True if unloaded, False if still active.
    """
    global _embedding_model, _last_used
    with _embedding_lock:
        if _embedding_model is None:
            return False  # Already unloaded
        if force or (time.time() - _last_used > IDLE_TIMEOUT):
            unload_model()
            return True
        return False


def unload_model() -> None:
    """Unload the model to free memory (useful for maintenance)."""
    global _embedding_model
    with _embedding_lock:
        if _embedding_model is not None:
            del _embedding_model
            _embedding_model = None
            logger.info("Embedding model unloaded")
