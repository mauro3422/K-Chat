"""Lifecycle helpers exposed through the API layer.

This keeps entrypoints from importing domain-layer reset hooks directly.
"""

from __future__ import annotations


def reset_runtime_state() -> None:
    """Reset process-local state used by the app lifecycle."""
    try:
        from src.logbus import reset_logbus
        reset_logbus()
    except Exception:
        pass

    try:
        from src.llm.model_registry import reset_model_registry
        reset_model_registry()
    except Exception:
        pass

    try:
        from src.llm.circuit_breaker import reset_breaker
        from src.llm.rate_limit_state import reset_rate_limit_store
        reset_breaker()
        reset_rate_limit_store()
    except Exception:
        pass

    try:
        from src.context.runtime import reset_context_cache
        reset_context_cache()
    except Exception:
        pass

    try:
        from src.config_loader import reset_dotenv_state
        reset_dotenv_state()
    except Exception:
        pass

    try:
        from src.llm.providers import reset_registry
        reset_registry()
    except Exception:
        pass

    try:
        from web.services.file_logger import reset_log_dirs
        reset_log_dirs()
    except Exception:
        pass

    try:
        from web.services.model_catalog import reset_model_cache
        reset_model_cache()
    except Exception:
        pass

    try:
        from src.llm.model_state import reset_state
        reset_state()
    except Exception:
        pass

    try:
        from src.llm.container import reset_container
        reset_container()
    except Exception:
        pass

    try:
        from src.memory.connection_pool import reset_connection_pool
        from src.memory.memory_pool import reset_memory_pool
        from src.memory.engine_state import reset_engine
        reset_connection_pool()
        reset_memory_pool()
        reset_engine()
    except Exception:
        pass

    try:
        from src.memory.embeddings.service import reset_model as reset_embedding_model
        from src.memory.retrieval.reranker import reset_reranker
        from src.memory.keywords.extractor import reset_global_extractor
        reset_embedding_model()
        reset_reranker()
        reset_global_extractor()
    except Exception:
        pass
