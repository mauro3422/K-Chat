import logging
import time
from typing import Any
from openai import RateLimitError
from src.llm.providers import *  # noqa: F403
from src.llm.providers import _get_provider, register_provider  # noqa: F401
from src.llm.model_state import *  # noqa: F403
from src.llm.model_state import _switch_model  # noqa: F401

logger: logging.Logger = logging.getLogger(__name__)

_MAX_RETRIES: int = 3
_RETRY_DELAY: float = 5.0


def _is_rate_limit_error(error: Exception) -> bool:
    if isinstance(error, RateLimitError):
        return True
    if getattr(error, "status_code", None) == 429:
        return True
    error_msg = str(error).lower()
    return "rate limit" in error_msg or "ratelimit" in error_msg or "429" in error_msg


def _api_call(**kwargs: Any) -> Any:
    """Wrapper over provider with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return _get_provider().chat(**kwargs)
        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                logger.warning("Rate limited for %s: %s", kwargs.get("model"), e)
                raise
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.debug("Retry %d/%d for %s in %.1fs: %s", attempt + 1, _MAX_RETRIES, kwargs.get("model"), delay, e)
                time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected error in _api_call")
