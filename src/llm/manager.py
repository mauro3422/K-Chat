import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from src.llm import models

logger: logging.Logger = logging.getLogger(__name__)

def verify_model(model_id: str) -> bool:
    """Tests if a model responds correctly by sending an ultra-short message."""
    try:
        models._api_call(
            model=model_id,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=2,
            timeout=2.0
        )
        return True
    except Exception as e:
        logger.warning("Model %s failed verification: %s", model_id, e)
        return False

def get_verified_models(force_refresh: bool = False) -> list[str]:
    """Returns the list of free models that are active and working."""
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

def get_default_model() -> str:
    """Selects the first model from PRIORITY that is available and has not failed. If the API does not respond, uses the fallback."""
    try:
        free_ids = [m.id for m in get_free_models()]
        for modelo in models.PRIORITY:
            if not models.is_model_failed(modelo):
                if modelo in free_ids or modelo == "big-pickle":
                    return modelo
    except Exception as e:
        logger.warning("Error getting models: %s", e)
    return models.FALLBACK_MODEL

def _mark_and_refresh(model: str) -> str:
    """Marks model as failed, refreshes verified list, and returns the alternative model."""
    try:
        get_verified_models(force_refresh=True)
    except Exception:
        logger.exception("Failed to refresh verified models")
    models.mark_model_failed(model)
    next_model = models._switch_model(model)
    return next_model
