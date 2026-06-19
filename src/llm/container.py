"""LLMContainer — dependency injection container for the LLM layer.

Centralizes creation and resolution of all LLM dependencies.

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
        self._lock = threading.RLock()

        # Lazy-init services
        self._circuit_breaker: Any = None
        self._rate_limit_store: Any = None
        self._model_state: Any = None
        self._provider: Any = None
        self._provider_registry: Any = None
        self._model_registry: Any = None

    def _get_or_create(self, attr: str, factory: Any) -> Any:
        with self._lock:
            value = getattr(self, attr)
            if value is None:
                value = factory()
                setattr(self, attr, value)
            return value

    # ── Config ────────────────────────────────────────────────────

    def get_config(self) -> Config:
        from src._config import resolve_config
        with self._lock:
            if self._config is None:
                self._config = resolve_config()
            return self._config

    # ── Circuit Breaker ───────────────────────────────────────────

    def get_circuit_breaker(self) -> Any:
        def factory() -> Any:
            from src.llm.circuit_breaker import CircuitBreaker
            return CircuitBreaker()
        return self._get_or_create("_circuit_breaker", factory)

    def set_circuit_breaker(self, breaker: Any | None) -> None:
        with self._lock:
            self._circuit_breaker = breaker

    # ── Rate Limit Store ─────────────────────────────────────────

    def get_rate_limit_store(self) -> Any:
        def factory() -> Any:
            from src.llm.rate_limit_state import ModelRateLimitStore
            return ModelRateLimitStore()
        return self._get_or_create("_rate_limit_store", factory)

    def set_rate_limit_store(self, store: Any | None) -> None:
        with self._lock:
            self._rate_limit_store = store

    # ── Model State ───────────────────────────────────────────────

    def get_model_state(self) -> Any:
        def factory() -> Any:
            from src.llm.model_state import ModelState
            from src.llm.model_state import PRIORITY, FALLBACK_MODEL
            return ModelState(
                priority=PRIORITY,
                fallback_model=FALLBACK_MODEL,
            )
        return self._get_or_create("_model_state", factory)

    def set_model_state(self, state: Any | None) -> None:
        with self._lock:
            self._model_state = state

    # ── Providers ─────────────────────────────────────────────────

    def get_provider_registry(self) -> Any:
        def factory() -> Any:
            from src.llm.providers import ProviderRegistry
            from src.llm.adapters import ADAPTERS
            provider_registry = ProviderRegistry()
            for name, adapter_cls in ADAPTERS.items():
                provider_registry.register(name, adapter_cls)
            return provider_registry
        return self._get_or_create("_provider_registry", factory)

    def set_provider_registry(self, registry: Any | None) -> None:
        with self._lock:
            self._provider_registry = registry

    def get_provider(self) -> Any:
        def factory() -> Any:
            from src.llm.providers import create_provider
            return create_provider(
                config=self.get_config(),
                registry=self.get_provider_registry(),
            )
        return self._get_or_create("_provider", factory)

    # ── Model Registry ────────────────────────────────────────────

    def get_model_registry(self) -> Any:
        def factory() -> Any:
            from src.llm.model_registry import ModelRegistry
            return ModelRegistry(
                config=self.get_config(),
                provider_registry=self.get_provider_registry(),
                provider_fn=self.get_provider,
            )
        return self._get_or_create("_model_registry", factory)

    def set_model_registry(self, registry: Any | None) -> None:
        with self._lock:
            self._model_registry = registry

def get_container(config: Config | None = None) -> LLMContainer:
    """Create a new container instance."""
    return LLMContainer(config=config)
