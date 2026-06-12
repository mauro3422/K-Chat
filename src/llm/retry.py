import logging
import time
from typing import Any, Callable
from openai import RateLimitError
from src.constants import LLM_MAX_RETRIES, LLM_RETRY_DELAY

logger: logging.Logger = logging.getLogger(__name__)


def is_rate_limit_error(error: Exception) -> bool:
    if isinstance(error, RateLimitError):
        return True
    if getattr(error, "status_code", None) == 429:
        return True
    error_msg = str(error).lower()
    return "rate limit" in error_msg or "ratelimit" in error_msg or "429" in error_msg


def execute_with_retry(fn: Callable[[], Any], model_name: str) -> Any:
    """Wrapper that executes a function with exponential backoff on rate limit or retryable errors."""
    last_error: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if is_rate_limit_error(e):
                logger.warning("Rate limited for %s: %s", model_name, e)
                if attempt < LLM_MAX_RETRIES - 1:
                    delay = LLM_RETRY_DELAY * (2 ** attempt)
                    logger.info("Rate limit detected. Retrying %d/%d in %.1fs...", attempt + 1, LLM_MAX_RETRIES, delay)
                    time.sleep(delay)
                    continue
                raise
            if attempt < LLM_MAX_RETRIES - 1:
                delay = LLM_RETRY_DELAY * (2 ** attempt)
                logger.debug("Retry %d/%d for %s in %.1fs: %s", attempt + 1, LLM_MAX_RETRIES, model_name, delay, e)
                time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected error in execute_with_retry")
