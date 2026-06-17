import logging
import threading
from typing import Any
from src.llm.protocol import LLMProvider
from src.llm.adapters import ADAPTERS

logger: logging.Logger = logging.getLogger(__name__)

# Thread-safety locks for lazy singletons
_registry_lock = threading.Lock()
_provider_lock = threading.Lock()


class ProviderRegistry:
    """Provider registry — register and look up LLM provider classes.

    Lego block: no framework imports, pure Python, injectable.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, type[LLMProvider]] = {}

    def register(self, name: str, cls: type[LLMProvider]) -> None:
        self._adapters[name] = cls

    def get(self, name: str) -> type[LLMProvider] | None:
        return self._adapters.get(name)


# ── Module-level lazy instance (no import-time side effects) ─────────
_registry: ProviderRegistry | None = None
_provider: LLMProvider | None = None


def _get_registry(registry: ProviderRegistry | None = None) -> ProviderRegistry:
    if registry is not None:
        return registry
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ProviderRegistry()
                for name, cls in ADAPTERS.items():
                    _registry.register(name, cls)
    return _registry


# Backward-compat aliases
register_provider = lambda name, cls: _get_registry().register(name, cls)
_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {}  # kept for tests that reassign it


def _reset_provider() -> None:
    global _provider
    with _provider_lock:
        _provider = None


# ── Container-aware factory ────────────────────────────────────────


def create_provider(config: Any | None = None, registry: ProviderRegistry | None = None) -> LLMProvider:
    """Create a provider using explicit dependency injection.

    Unlike _get_provider(), this does NOT use module-level singletons.
    Callers can pass config and registry directly.
    """
    from src._config import resolve_config
    cfg = resolve_config(config)

    if registry is None:
        registry = _get_registry()

    provider_class = registry.get(cfg.llm_provider)
    if provider_class is None:
        raise ValueError(f"Unknown provider: {cfg.llm_provider}")

    api_key = cfg.opencode_zen_api_key
    base_url = cfg.opencode_zen_base_url
    if cfg.llm_mode == "go":
        base_url = cfg.opencode_go_base_url

    return provider_class(api_key=api_key, base_url=base_url)


def _get_provider(config: Any | None = None, registry: ProviderRegistry | None = None) -> LLMProvider:
    # TODO: Migrate to create_provider() via container — this singleton will be removed
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                if config is None:
                    from src.config_loader import load_config
                    config = load_config()
                reg = registry or _get_registry()
                provider_name = config.llm_provider
                cls = reg.get(provider_name)
                if cls is None:
                    raise ValueError(f"Unknown LLM provider: {provider_name}")
                base_url = config.opencode_go_base_url if config.llm_mode == "go" else config.opencode_zen_base_url
                _provider = cls(api_key=config.opencode_zen_api_key, base_url=base_url)
    return _provider


__all__ = [
    "ProviderRegistry",
    "register_provider",
    "_get_provider",
    "_provider",
    "_reset_provider",
]
