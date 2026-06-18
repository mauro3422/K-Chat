import logging
from typing import Any

from src.llm.adapters import ADAPTERS
from src.llm.protocol import LLMProvider

logger: logging.Logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Provider registry — register and look up LLM provider classes."""

    def __init__(self) -> None:
        self._adapters: dict[str, type[LLMProvider]] = {}

    def register(self, name: str, cls: type[LLMProvider]) -> None:
        self._adapters[name] = cls

    def get(self, name: str) -> type[LLMProvider] | None:
        return self._adapters.get(name)


_registry: ProviderRegistry | None = None


def configure_registry(registry: ProviderRegistry | None) -> None:
    """Set the active provider registry explicitly, or clear it with None."""
    global _registry
    _registry = registry


def reset_registry() -> None:
    """Clear the cached provider registry and restore lazy construction."""
    configure_registry(None)


def _get_registry(registry: ProviderRegistry | None = None) -> ProviderRegistry:
    if registry is not None:
        return registry
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        for name, cls in ADAPTERS.items():
            _registry.register(name, cls)
    return _registry


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    _get_registry().register(name, cls)


def create_provider(config: Any | None = None, registry: ProviderRegistry | None = None) -> LLMProvider:
    """Create a provider using explicit dependency injection."""
    from src._config import resolve_config

    cfg = resolve_config(config)
    registry = _get_registry(registry)

    provider_class = registry.get(cfg.llm_provider)
    if provider_class is None:
        raise ValueError(f"Unknown provider: {cfg.llm_provider}")

    base_url = cfg.opencode_go_base_url if cfg.llm_mode == "go" else cfg.opencode_zen_base_url
    return provider_class(api_key=cfg.opencode_zen_api_key, base_url=base_url)


def _get_provider(config: Any | None = None, registry: ProviderRegistry | None = None) -> LLMProvider:
    """Backward-compatible wrapper around create_provider()."""
    return create_provider(config=config, registry=registry)


__all__ = [
    "ProviderRegistry",
    "configure_registry",
    "reset_registry",
    "register_provider",
    "create_provider",
    "_get_provider",
    "_get_registry",
]
