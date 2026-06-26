import logging
import copy
from typing import Any

from src.llm.retry import execute_with_retry
from src.llm.protocol import LLMProvider, UnifiedRequest

logger: logging.Logger = logging.getLogger(__name__)


def _resolve_provider(
    provider: LLMProvider | None = None,
    provider_fn: Any | None = None,
    model_name: str = "",
) -> LLMProvider:
    if provider is not None:
        return provider
    if provider_fn is not None:
        return provider_fn()
    from src.llm.providers import create_provider
    if model_name.endswith("-free"):
        from src._config import resolve_config

        cfg = copy.copy(resolve_config())
        cfg.llm_mode = "zen"
        return create_provider(cfg)
    return create_provider()


async def _api_call(
    provider: LLMProvider | None = None,
    provider_fn: Any | None = None,
    **kwargs: Any,
) -> Any:
    """Wrapper over provider with exponential backoff retry logic."""
    model_name = kwargs.get("model", "unknown-model")
    prov = _resolve_provider(provider, provider_fn, model_name=model_name)
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
        return await execute_with_retry(lambda: prov.chat_stream(req), model_name, timeout=60.0)
    return await execute_with_retry(lambda: prov.chat(req), model_name, timeout=60.0)


