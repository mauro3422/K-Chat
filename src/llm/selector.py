import inspect
import logging

import src.llm.model_state as models
import src.llm.model_registry as registry
import src.llm.discovery as discovery
from src.config_loader import SECONDARY_MODEL
from src.utils.async_utils import run_awaitable_sync

logger: logging.Logger = logging.getLogger(__name__)


def _get_free_models_sync(free_models_fn=None) -> list:
    """Get free models, handling both sync and async versions."""
    result = (free_models_fn or discovery.get_free_models)()
    if inspect.isawaitable(result):
        return run_awaitable_sync(result, label="free-model lookup")
    return result


def _get_default_model_candidates(
    verified_models_fn=None,
    free_models_fn=None,
) -> tuple[list[str], bool]:
    cached_verified = (verified_models_fn or registry.get_verified_models)()
    if cached_verified:
        return cached_verified, True
    free_models = _get_free_models_sync(free_models_fn=free_models_fn)
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
