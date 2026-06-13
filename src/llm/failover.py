import logging

import src.llm.models as models
import src.llm.discovery as discovery

logger: logging.Logger = logging.getLogger(__name__)


def _mark_and_refresh(model: str, refresh: bool = True) -> str:
    """Marks model as failed, refreshes verified list, and returns the alternative model."""
    if refresh:
        try:
            discovery.get_verified_models(force_refresh=True)
        except Exception:
            logger.exception("Failed to refresh verified models")
    models.mark_model_failed(model)
    try:
        next_model = models._switch_model(model)
    except RuntimeError:
        logger.critical("All models have failed! Using last resort: %s", model)
        next_model = model  # last resort
    return next_model
