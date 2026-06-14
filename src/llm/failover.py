import logging

import src.llm.model_state as models
import src.llm.discovery as discovery
from src.llm.rate_limit_state import get_rate_limit_store
from src.llm.retry import is_rate_limit_error

logger: logging.Logger = logging.getLogger(__name__)


def _mark_and_refresh(model: str, refresh: bool = True, error: Exception | None = None) -> str:
    """Marks model as failed, refreshes verified list, and returns the alternative model.

    If the error was a rate limit, also records the cooldown period so the UI
    can show when the model will be available again.
    """
    if refresh:
        try:
            discovery.get_verified_models(force_refresh=True)
        except Exception:
            logger.exception("Failed to refresh verified models")

    models.mark_model_failed(model)

    # Track rate limit separately with cooldown
    if error is not None and is_rate_limit_error(error):
        store = get_rate_limit_store()
        detail = str(error)[:200]
        store.mark_rate_limited(model, retry_after=60.0, detail=detail)
        logger.warning("Rate limit recorded for %s — will retry after cooldown", model)

    try:
        next_model = models._switch_model(model)
    except RuntimeError:
        logger.critical("All models have failed! Using last resort: %s", model)
        next_model = model  # last resort
    return next_model
