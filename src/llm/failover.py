import inspect
import logging

import src.llm.discovery as discovery
import src.llm.model_state as models
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


def _is_not_supported_error(error: Exception | None) -> bool:
    return error is not None and "not supported" in str(error).lower()


def _append_unique(target: list[str], values: list[str]) -> None:
    seen = set(target)
    for value in values:
        if value and value not in seen:
            target.append(value)
            seen.add(value)


def _preferred_fallbacks() -> tuple[str, ...]:
    return ("deepseek-v4-flash", "deepseek-v4-flash-free")


def _dynamic_switch_model(failed_model: str, *, registry=None, rate_store=None) -> str | None:
    """Choose a dynamic fallback from verified/free models before static priority."""
    reg = registry or _resolve_registry()
    candidates: list[str] = []
    for getter in ("get_verified_models", "get_free_candidates", "get_all_models"):
        fn = getattr(reg, getter, None)
        if not callable(fn):
            continue
        try:
            _append_unique(candidates, list(fn()))
        except Exception:
            logger.debug("Could not read %s from model registry", getter, exc_info=True)

    preferred = [model for model in _preferred_fallbacks() if model in candidates]
    free = [model for model in candidates if model.endswith("-free") and model not in preferred]
    ordered = [*preferred, *free, *candidates]

    for candidate in ordered:
        if candidate == failed_model:
            continue
        if models.is_model_failed(candidate):
            continue
        if rate_store is not None:
            if getattr(rate_store, "is_unavailable", lambda _model: False)(candidate):
                continue
            if getattr(rate_store, "is_rate_limited", lambda _model: False)(candidate):
                continue
        return candidate
    return None


def _mark_and_refresh(
    model: str,
    refresh: bool = True,
    error: Exception | None = None,
    breaker=None,
    rate_store=None,
    registry=None,
) -> str:
    """Marks model as failed, refreshes verified list, and returns an alternative."""
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

    if error is not None:
        err_str = str(error)
        if is_rate_limit_error(error):
            detail = err_str[:200]
            rate_store.mark_rate_limited(model, retry_after=60.0, detail=detail)
            logger.warning("Rate limit recorded for %s; will retry after cooldown", model)
        elif _is_not_supported_error(error):
            rate_store.mark_unavailable(model)
            try:
                (registry or _resolve_registry()).remove_verified_model(model)
            except Exception:
                logger.warning("Failed to remove unsupported model from registry", exc_info=True)
            logger.warning("Model %s marked unavailable: not supported by provider", model)
        elif "insufficient balance" in err_str.lower():
            try:
                (registry or _resolve_registry()).mark_quota_exhausted()
                logger.warning("Go quota exhausted detected for model %s", model)
            except Exception:
                logger.warning("Failed to mark quota exhausted", exc_info=True)

    dynamic_model = _dynamic_switch_model(model, registry=registry, rate_store=rate_store)
    if dynamic_model:
        return dynamic_model

    try:
        next_model = models._switch_model(model)
    except RuntimeError:
        if not breaker.is_available(model):
            raise RuntimeError("All models are circuit-broken; no LLM available")
        logger.critical("All models have failed! Using last resort: %s", model)
        next_model = model
    return next_model
