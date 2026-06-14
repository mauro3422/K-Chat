import logging
from typing import Any
from src.llm.protocol import LLMProvider
from src.llm.adapters import ADAPTERS

logger: logging.Logger = logging.getLogger(__name__)

__all__ = ["register_provider", "_get_provider", "_provider"]

_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {}


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    _PROVIDER_REGISTRY[name] = cls


for name, cls in ADAPTERS.items():
    register_provider(name, cls)

_provider: LLMProvider | None = None


def _reset_provider() -> None:
    global _provider
    _provider = None


def _get_provider(config: Any | None = None) -> LLMProvider:
    global _provider
    if _provider is None:
        from src.config_loader import DEFAULT_CONFIG
        cfg = config or DEFAULT_CONFIG
        provider_name = cfg.llm_provider
        cls = _PROVIDER_REGISTRY.get(provider_name)
        if cls is None:
            raise ValueError(f"Unknown LLM provider: {provider_name}")
        base_url = cfg.opencode_go_base_url if cfg.llm_mode == "go" else cfg.opencode_zen_base_url
        _provider = cls(api_key=cfg.opencode_zen_api_key, base_url=base_url)
    return _provider
