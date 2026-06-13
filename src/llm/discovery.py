import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import src.llm.models as models
import src.llm.verifier as verifier

logger: logging.Logger = logging.getLogger(__name__)


def get_models(force_refresh: bool = False) -> list[Any]:
    """Returns all available models from the API (with in-memory cache)."""
    cached = models.get_cached_models_safe()
    if cached is None or force_refresh:
        try:
            result = list(models._get_provider().list_models())
            models.set_cached_models(result)
        except Exception as e:
            logger.error("Error fetching models from API: %s", e)
            cached = models.get_cached_models_safe()
            if cached is not None:
                return cached
            raise
    return models.get_cached_models_safe() or []


def get_free_models(force_refresh: bool = False) -> list[Any]:
    """Returns only free models (IDs ending in -free)."""
    all_models = get_models(force_refresh=force_refresh)
    return [model for model in all_models if model.id.endswith("-free")]


def get_verified_models(force_refresh: bool = False) -> list[str]:
    """Returns the list of free models that are active and working."""
    cached = models.get_verified_models_safe()
    if cached is None or force_refresh:
        try:
            free_models = get_free_models(force_refresh=force_refresh)
            verified: list[str] = []

            def check(model_id: str) -> str | None:
                if verifier.verify_model(model_id):
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
