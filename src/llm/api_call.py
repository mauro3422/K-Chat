import asyncio
import logging
from typing import Any

from src.llm.providers import _get_provider
from src.llm.retry import execute_with_retry
from src.llm.protocol import UnifiedRequest

logger: logging.Logger = logging.getLogger(__name__)


async def _api_call(**kwargs: Any) -> Any:
    """Wrapper over provider with exponential backoff retry logic."""
    model_name = kwargs.get("model", "unknown-model")
    is_stream = kwargs.get("stream", False)
    req = UnifiedRequest(
        messages=kwargs.get("messages", []),
        model=model_name,
        tools=kwargs.get("tools"),
        stream=is_stream,
        temperature=kwargs.get("temperature"),
        max_tokens=kwargs.get("max_tokens") or 32768,
    )
    if is_stream:
        return await execute_with_retry(lambda: _get_provider().chat_stream(req), model_name, timeout=60.0)
    return await execute_with_retry(lambda: _get_provider().chat(req), model_name, timeout=60.0)


