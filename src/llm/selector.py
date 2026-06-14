import asyncio
import inspect
import logging

import src.llm.model_state as models
import src.llm.discovery as discovery
from src.config_loader import SECONDARY_MODEL

logger: logging.Logger = logging.getLogger(__name__)


def _get_free_models_sync() -> list:
    """Get free models, handling both sync and async versions."""
    result = discovery.get_free_models()
    if inspect.isawaitable(result):
        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, result)
                return future.result(timeout=30)
        except RuntimeError:
            return asyncio.run(result)
    return result


def _get_default_model_candidates() -> tuple[list[str], bool]:
    cached_verified = models.get_verified_models_safe()
    if cached_verified:
        return cached_verified, True
    free_models = _get_free_models_sync()
    return [m.id for m in free_models], False


def get_default_model() -> str:
    """Selects the first model from PRIORITY that is available and has not failed."""
    try:
        available_ids, verified_cache_used = _get_default_model_candidates()
        for modelo in models.PRIORITY:
            if not models.is_model_failed(modelo):
                if modelo in available_ids or (modelo == SECONDARY_MODEL and not verified_cache_used):
                    return modelo
    except Exception as e:
        logger.warning("Error getting models: %s", e)
    return models.FALLBACK_MODEL
