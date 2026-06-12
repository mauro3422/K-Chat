"""Compatibility wrapper for legacy LLM policy imports.

The real implementation lives in `src.llm.policy`.
This module preserves the old patch points used by tests and callers.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from src.llm import models
from src.llm import policy as _policy

logger: logging.Logger = logging.getLogger(__name__)


def verify_model(model_id: str) -> bool:
    return _policy.verify_model(model_id)


def get_models(force_refresh: bool = False) -> list[Any]:
    return _policy.get_models(force_refresh=force_refresh)


def get_free_models(force_refresh: bool = False) -> list[Any]:
    all_models = get_models(force_refresh=force_refresh)
    return [model for model in all_models if model.id.endswith("-free")]


def get_verified_models(force_refresh: bool = False) -> list[str]:
    cached = models.get_verified_models_safe()
    if cached is None or force_refresh:
        try:
            free_models = get_free_models(force_refresh=force_refresh)
            verified: list[str] = []

            def check(model_id: str) -> str | None:
                if verify_model(model_id):
                    return model_id
                return None

            with ThreadPoolExecutor(max_workers=max(1, len(free_models))) as executor:
                results = executor.map(check, [m.id for m in free_models])
                for res in results:
                    if res:
                        verified.append(res)
            models.set_verified_models(verified)
        except Exception as e:
            logger.error("Error verifying models: %s", e)
            cached = models.get_verified_models_safe()
            if cached is not None:
                return cached
            models.set_verified_models([models.FALLBACK_MODEL])
    return models.get_verified_models_safe() or []


def _get_default_model_candidates() -> tuple[list[str], bool]:
    cached_verified = models.get_verified_models_safe()
    if cached_verified:
        return cached_verified, True
    return [m.id for m in get_free_models()], False


def get_default_model() -> str:
    try:
        available_ids, verified_cache_used = _get_default_model_candidates()
        for modelo in models.PRIORITY:
            if not models.is_model_failed(modelo):
                if modelo in available_ids or (modelo == "big-pickle" and not verified_cache_used):
                    return modelo
    except Exception as e:
        logger.warning("Error getting models: %s", e)
    return models.FALLBACK_MODEL


def _mark_and_refresh(model: str, refresh: bool = True) -> str:
    if refresh:
        try:
            get_verified_models(force_refresh=True)
        except Exception:
            logger.exception("Failed to refresh verified models")
    models.mark_model_failed(model)
    next_model = models._switch_model(model)
    return next_model


__all__ = [
    "verify_model",
    "get_verified_models",
    "get_models",
    "get_free_models",
    "get_default_model",
    "_mark_and_refresh",
]
