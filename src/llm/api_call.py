import logging
from typing import Any

from src.llm.providers import _get_provider
from src.llm.retry import execute_with_retry

logger: logging.Logger = logging.getLogger(__name__)


def _api_call(**kwargs: Any) -> Any:
    """Wrapper over provider with exponential backoff retry logic."""
    model_name = kwargs.get("model", "unknown-model")
    is_stream = kwargs.get("stream", False)
    if is_stream:
        return execute_with_retry(lambda: _get_provider().chat_stream(**kwargs), model_name)
    return execute_with_retry(lambda: _get_provider().chat(**kwargs), model_name)

