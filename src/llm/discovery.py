import asyncio
import logging
from typing import Any

import src.llm.model_state as models
from src.llm.providers import _get_provider
import src.llm.verifier as verifier

logger: logging.Logger = logging.getLogger(__name__)


async def get_models(force_refresh: bool = False) -> list[Any]:
    """Returns all available models from the API (with in-memory cache)."""
    cached = models.get_cached_models_safe()
    if cached is None or force_refresh:
        try:
            provider = _get_provider()
            result = await provider.list_models()
            models.set_cached_models(result)
        except Exception as e:
            logger.error("Error fetching models from API: %s", e)
            cached = models.get_cached_models_safe()
            if cached is not None:
                return cached
            raise
    return models.get_cached_models_safe() or []


async def get_free_models(force_refresh: bool = False) -> list[Any]:
    """Returns only free models (IDs ending in -free)."""
    all_models = await get_models(force_refresh=force_refresh)
    free_models = []
    for model in all_models:
        model_id = model if isinstance(model, str) else getattr(model, "id", None)
        if model_id and model_id.endswith("-free"):
            free_models.append(model)
    return free_models


async def get_verified_models(force_refresh: bool = False) -> list[str]:
    """Returns the list of free models that are active and working."""
    cached = models.get_verified_models_safe()
    if cached is None or force_refresh:
        try:
            free_models = await get_free_models(force_refresh=force_refresh)
            verified: list[str] = []

            model_ids = [m if isinstance(m, str) else getattr(m, "id", "") for m in free_models]
            model_ids = [mid for mid in model_ids if mid]

            async def check(model_id: str) -> str | None:
                if await verifier.verify_model(model_id):
                    return model_id
                return None

            tasks = [check(mid) for mid in model_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, str):
                    verified.append(res)
            models.set_verified_models(verified)
        except Exception as e:
            logger.error("Error verifying models: %s", e)
            cached = models.get_verified_models_safe()
            if cached is not None:
                return cached
            models.set_verified_models([models.FALLBACK_MODEL])
    return models.get_verified_models_safe() or []
