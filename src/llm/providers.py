import logging
import os
from src.llm.protocol import LLMProvider
from src.llm.openai_provider import OpenAIProvider

logger: logging.Logger = logging.getLogger(__name__)

__all__ = ["register_provider", "_get_provider", "_provider"]

_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {}


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    _PROVIDER_REGISTRY[name] = cls


register_provider("openai", OpenAIProvider)

_provider: LLMProvider | None = None


def _get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        provider_name = os.environ.get("LLM_PROVIDER", "openai")
        cls = _PROVIDER_REGISTRY.get(provider_name, OpenAIProvider)
        _provider = cls()
    return _provider
