import logging

import src.llm.models as models
import src.llm.discovery as discovery

logger: logging.Logger = logging.getLogger(__name__)


def _get_default_model_candidates() -> tuple[list[str], bool]:
    cached_verified = models.get_verified_models_safe()
    if cached_verified:
        return cached_verified, True
    return [m.id for m in discovery.get_free_models()], False


def get_default_model() -> str:
    """Selects the first model from PRIORITY that is available and has not failed."""
    try:
        available_ids, verified_cache_used = _get_default_model_candidates()
        for modelo in models.PRIORITY:
            if not models.is_model_failed(modelo):
                if modelo in available_ids or (modelo == "big-pickle" and not verified_cache_used):
                    return modelo
    except Exception as e:
        logger.warning("Error getting models: %s", e)
    return models.FALLBACK_MODEL
