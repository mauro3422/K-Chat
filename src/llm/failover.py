import asyncio
import inspect
import logging
import threading

import src.llm.model_state as models
import src.llm.discovery as discovery
from src.llm.circuit_breaker import get_breaker
from src.llm.rate_limit_state import get_rate_limit_store
from src.llm.retry import is_rate_limit_error

logger: logging.Logger = logging.getLogger(__name__)


def _refresh_verified_models_background(result) -> None:
    async def _consume() -> None:
        try:
            await result
        except Exception:
            logger.exception("Failed to refresh verified models")

    try:
        asyncio.run(_consume())
    except Exception:
        logger.exception("Failed to refresh verified models")


def _resolve_breaker():
    """Get circuit breaker, preferring container if available."""
    try:
        from src.llm.container import get_container
        return get_container().get_circuit_breaker()
    except Exception:
        return get_breaker()


def _resolve_rate_store():
    """Get rate limit store, preferring container if available."""
    try:
        from src.llm.container import get_container
        return get_container().get_rate_limit_store()
    except Exception:
        return get_rate_limit_store()


def _resolve_registry():
    """Get model registry, preferring container if available."""
    try:
        from src.llm.container import get_container
        return get_container().get_model_registry()
    except Exception:
        from src.llm.model_registry import get_model_registry
        return get_model_registry()


def _mark_and_refresh(model: str, refresh: bool = True, error: Exception | None = None) -> str:
    """Marks model as failed, refreshes verified list, and returns the alternative model.

    If the error was a rate limit, also records the cooldown period so the UI
    can show when the model will be available again.
    """
    if refresh:
        try:
            result = discovery.get_verified_models(force_refresh=True)
            if inspect.isawaitable(result):
                threading.Thread(target=_refresh_verified_models_background, args=(result,), daemon=True).start()
        except Exception:
            logger.exception("Failed to refresh verified models")

    breaker = _resolve_breaker()
    rate_store = _resolve_rate_store()

    models.mark_model_failed(model)
    breaker.record_failure(model)

    # Track rate limit separately with cooldown
    if error is not None:
        err_str = str(error)
        if is_rate_limit_error(error):
            detail = err_str[:200]
            rate_store.mark_rate_limited(model, retry_after=60.0, detail=detail)
            logger.warning("Rate limit recorded for %s — will retry after cooldown", model)
        elif "insufficient balance" in err_str.lower():
            # Go quota exhausted — mark registry so UI can show a warning
            try:
                _resolve_registry().mark_quota_exhausted()
                logger.warning("Go quota exhausted detected for model %s", model)
            except Exception:
                pass

    try:
        next_model = models._switch_model(model)
    except RuntimeError:
        if not breaker.is_available(model):
            raise RuntimeError("All models are circuit-broken — no LLM available")
        logger.critical("All models have failed! Using last resort: %s", model)
        next_model = model  # last resort
    return next_model
