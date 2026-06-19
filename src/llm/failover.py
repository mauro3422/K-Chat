import asyncio
import inspect
import logging

import src.llm.model_state as models
import src.llm.discovery as discovery
from src.llm.circuit_breaker import get_breaker
from src.llm.rate_limit_state import get_rate_limit_store
from src.llm.retry import is_rate_limit_error
from src.utils.async_utils import schedule_background_awaitable

logger: logging.Logger = logging.getLogger(__name__)


def _refresh_verified_models_background(result) -> None:
    schedule_background_awaitable(result, label="verified models refresh")


def _resolve_breaker():
    """Get the active circuit breaker."""
    return get_breaker()


def _resolve_rate_store():
    """Get the active rate limit store."""
    return get_rate_limit_store()


def _resolve_registry():
    """Get the active model registry."""
    from src.llm.model_registry import get_model_registry
    return get_model_registry()


def _mark_and_refresh(
    model: str,
    refresh: bool = True,
    error: Exception | None = None,
    breaker=None,
    rate_store=None,
    registry=None,
) -> str:
    """Marks model as failed, refreshes verified list, and returns the alternative model.

    If the error was a rate limit, also records the cooldown period so the UI
    can show when the model will be available again.
    """
    if refresh:
        try:
            result = discovery.get_verified_models(force_refresh=True)
            if inspect.isawaitable(result):
                _refresh_verified_models_background(result)
        except Exception:
            logger.exception("Failed to refresh verified models")

    breaker = breaker or _resolve_breaker()
    rate_store = rate_store or _resolve_rate_store()

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
                (registry or _resolve_registry()).mark_quota_exhausted()
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
