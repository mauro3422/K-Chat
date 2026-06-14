import logging
import asyncio
from typing import Any, Callable, Awaitable
from openai import RateLimitError
from src.config_loader import DEFAULT_CONFIG

logger: logging.Logger = logging.getLogger(__name__)


def is_rate_limit_error(error: Exception) -> bool:
    if isinstance(error, RateLimitError):
        return True
    if getattr(error, "status_code", None) == 429:
        return True
    error_msg = str(error).lower()
    return "rate limit" in error_msg or "ratelimit" in error_msg or "429" in error_msg


async def execute_with_retry(fn: Callable[[], Awaitable[Any] | Any], model_name: str, max_retries: int | None = None, retry_delay: float | None = None) -> Any:
    """Wrapper that executes an async function with exponential backoff on rate limit or retryable errors."""
    last_error: Exception | None = None
    if max_retries is None:
        max_retries = DEFAULT_CONFIG.llm_max_retries
    if retry_delay is None:
        retry_delay = DEFAULT_CONFIG.llm_retry_delay
    for attempt in range(max_retries):
        try:
            res = fn()
            if asyncio.iscoroutine(res):
                return await res
            return res
        except Exception as e:
            last_error = e
            if is_rate_limit_error(e):
                logger.warning("Rate limited for %s: %s", model_name, e)
                if attempt < max_retries - 1:
                    delay = retry_delay * (2 ** attempt)
                    logger.info("Rate limit detected. Retrying %d/%d in %.1fs...", attempt + 1, max_retries, delay)
                    await asyncio.sleep(delay)
                    continue
                raise
            raise e
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected error in execute_with_retry")
