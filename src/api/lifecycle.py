"""Lifecycle helpers exposed through the API layer.

This keeps entrypoints from importing domain-layer reset hooks directly.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def reset_runtime_state() -> None:
    """Reset process-local state used by the app lifecycle."""
    try:
        from src.logbus import reset_logbus
        reset_logbus()
    except Exception:
        logger.warning("Failed to reset logbus", exc_info=True)

    try:
        from src.llm.model_registry import reset_model_registry
        reset_model_registry()
    except Exception:
        logger.warning("Failed to reset model registry", exc_info=True)

    try:
        from src.llm.circuit_breaker import reset_breaker
        from src.llm.rate_limit_state import reset_rate_limit_store
        reset_breaker()
        reset_rate_limit_store()
    except Exception:
        logger.warning("Failed to reset circuit breaker or rate limit store", exc_info=True)

    try:
        from src.context.runtime import reset_context_cache
        reset_context_cache()
    except Exception:
        logger.warning("Failed to reset context cache", exc_info=True)

    try:
        from src.context.templates import reset_templates_cache
        reset_templates_cache()
    except Exception:
        logger.warning("Failed to reset templates cache", exc_info=True)

    try:
        from src.config_loader import reset_dotenv_state
        reset_dotenv_state()
    except Exception:
        logger.warning("Failed to reset dotenv state", exc_info=True)

    try:
        from src.llm.providers import reset_registry
        reset_registry()
    except Exception:
        logger.warning("Failed to reset LLM providers registry", exc_info=True)

    try:
        from src.llm.model_state import reset_state
        reset_state()
    except Exception:
        logger.warning("Failed to reset model state", exc_info=True)

    try:
        from src.memory.connection_pool import reset_connection_pool
        from src.memory.memory_pool import reset_memory_pool
        from src.memory.engine_state import reset_engine
        reset_connection_pool()
        reset_memory_pool()
        reset_engine()
    except Exception:
        logger.warning("Failed to reset memory pools/engine", exc_info=True)

    try:
        from src.memory.embeddings.service import reset_model as reset_embedding_model
        from src.memory.retrieval.reranker import reset_reranker
        from src.memory.keywords.extractor import reset_global_extractor
        reset_embedding_model()
        reset_reranker()
        reset_global_extractor()
    except Exception:
        logger.warning("Failed to reset embedding/reranker/extractor", exc_info=True)

    try:
        from src.utils.async_utils import reset_thread_pool
        reset_thread_pool()
    except Exception:
        logger.warning("Failed to reset thread pool", exc_info=True)
