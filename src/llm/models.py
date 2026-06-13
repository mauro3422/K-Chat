import logging
import time
from typing import Any
from openai import RateLimitError
from src.llm.providers import _get_provider
from src.llm.model_state import (
    PRIORITY,
    FALLBACK_MODEL,
    is_model_failed,
    mark_model_failed,
    get_verified_models_safe,
    set_verified_models,
    get_cached_models_safe,
    set_cached_models,
    _switch_model,
    clear_failed_models,
)
from src.llm.retry import execute_with_retry, is_rate_limit_error

logger: logging.Logger = logging.getLogger(__name__)

# Keep alias for backward compatibility/external callers
_is_rate_limit_error = is_rate_limit_error


def _api_call(**kwargs: Any) -> Any:
    """Wrapper over provider with exponential backoff retry logic."""
    model_name = kwargs.get("model", "unknown-model")
    return execute_with_retry(lambda: _get_provider().chat(**kwargs), model_name)


