"""LLMContainer — dependency injection container for the LLM layer.

Centralizes creation and resolution of all LLM dependencies.
Replaces module-level singletons gradually.

Usage:
    container = LLMContainer(config)
    provider = container.get_provider()
    result = await container.chat_fn(messages)
"""

from __future__ import annotations

import threading
from typing import Any

from src.config_loader import Config


class LLMContainer:
    """DI container for LLM layer services."""

    def __init__(self, config: Config | None = None):
        self._config = config
        self._lock = threading.Lock()

        # Lazy-init services
        self._circuit_breaker: Any = None
        self._rate_limit_store: Any = None
        self._model_state: Any = None
        self._provider: Any = None
        self._provider_registry: Any = None
        self._model_registry: Any = None

    # ── Config ────────────────────────────────────────────────────

    def get_config(self) -> Config:
        from src._config import resolve_config
        if self._config is None:
            self._config = resolve_config()
        return self._config

    # ── Circuit Breaker ───────────────────────────────────────────

    def get_circuit_breaker(self) -> Any:
        if self._circuit_breaker is None:
            from src.llm.circuit_breaker import CircuitBreaker
            self._circuit_breaker = CircuitBreaker()
        return self._circuit_breaker

    # ── Rate Limit Store ─────────────────────────────────────────

    def get_rate_limit_store(self) -> Any:
        if self._rate_limit_store is None:
            from src.llm.rate_limit_state import ModelRateLimitStore
            self._rate_limit_store = ModelRateLimitStore()
        return self._rate_limit_store

    # ── Model State ───────────────────────────────────────────────

    def get_model_state(self) -> Any:
        if self._model_state is None:
            from src.llm.model_state import ModelState
            from src.config_loader import DEFAULT_MODEL, SECONDARY_MODEL
            self._model_state = ModelState(
                priority=[DEFAULT_MODEL] + list(SECONDARY_MODEL or []),
                fallback_model=DEFAULT_MODEL,
            )
        return self._model_state

    # ── Providers ─────────────────────────────────────────────────

    def get_provider_registry(self) -> Any:
        if self._provider_registry is None:
            from src.llm.providers import ProviderRegistry
            from src.llm.adapters import ADAPTERS
            self._provider_registry = ProviderRegistry()
            for name, adapter_cls in ADAPTERS.items():
                self._provider_registry.register(name, adapter_cls)
        return self._provider_registry

    def get_provider(self) -> Any:
        if self._provider is None:
            from src.llm.providers import create_provider
            self._provider = create_provider(
                config=self.get_config(),
                registry=self.get_provider_registry(),
            )
        return self._provider

    # ── Model Registry ────────────────────────────────────────────

    def get_model_registry(self) -> Any:
        if self._model_registry is None:
            from src.llm.model_registry import ModelRegistry
            self._model_registry = ModelRegistry(
                config=self.get_config(),
                provider_registry=self.get_provider_registry(),
                provider_fn=self.get_provider,
            )
        return self._model_registry


# Default global container (backward compat while migration is in progress)
_default_container: LLMContainer | None = None
_default_lock = threading.Lock()


def get_container(config: Config | None = None) -> LLMContainer:
    """Get the default container (creates if needed)."""
    global _default_container
    if _default_container is None:
        with _default_lock:
            if _default_container is None:
                _default_container = LLMContainer(config=config)
    return _default_container


def reset_container() -> None:
    """Reset the default container (for testing)."""
    global _default_container
    with _default_lock:
        _default_container = None
