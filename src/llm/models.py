import logging
import time
from typing import Any
from src.llm.providers import *  # noqa: F403
from src.llm.providers import _get_provider, register_provider  # noqa: F401
from src.llm.model_state import *  # noqa: F403
from src.llm.model_state import _switch_model  # noqa: F401

logger: logging.Logger = logging.getLogger(__name__)

_MAX_RETRIES: int = 1
_RETRY_DELAY: float = 0.5


def _api_call(**kwargs: Any) -> Any:
    """Wrapper over provider with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return _get_provider().chat(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.debug("Retry %d/%d for %s in %.1fs: %s", attempt + 1, _MAX_RETRIES, kwargs.get("model"), delay, e)
                time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected error in _api_call")
