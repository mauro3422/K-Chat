"""Model failure state tracking.

This module ONLY tracks which models have failed and manages model switching.
Model discovery and verification are in model_registry.py.

Do NOT add verified model tracking here â€” use model_registry instead.
"""

import logging
from contextvars import ContextVar
import threading
from typing import Any

from src.config_loader import DEFAULT_MODEL, SECONDARY_MODEL

logger: logging.Logger = logging.getLogger(__name__)


class ModelState:
    def __init__(self, priority=None, fallback_model=None):
        self._lock = threading.Lock()
        self._priority = [m for m in (priority or [DEFAULT_MODEL, SECONDARY_MODEL]) if m]
        self._fallback_model = fallback_model or DEFAULT_MODEL
        self._failed_models: set[str] = set()
        self._cached_models: list[Any] | None = None

    @property
    def priority(self) -> list[str]:
        return list(self._priority)

    @property
    def fallback_model(self) -> str:
        return self._fallback_model

    def is_model_failed(self, model: str) -> bool:
        with self._lock:
            return model in self._failed_models

    def mark_model_failed(self, model: str) -> None:
        with self._lock:
            self._failed_models.add(model)

    def clear_failed_models(self) -> None:
        with self._lock:
            self._failed_models.clear()

    def get_cached_models_safe(self) -> Any:
        with self._lock:
            return self._cached_models

    def set_cached_models(self, value: Any) -> None:
        with self._lock:
            self._cached_models = value

    def _candidates(self) -> list[str]:
        """Return candidate models in priority order for failover."""
        return self._priority

    def switch_model(self, model: str) -> str:
        """Switch to an alternative model. NEVER returns a failed model.

        Uses verified models from discovery if available (so the bot uses
        the same auto-discovery as the web UI). Falls back to priority list.

        If all models failed: raises RuntimeError.
        """
        candidates = self._candidates()
        with self._lock:
            # First try candidates that aren't failed
            for m in candidates:
                if m not in self._failed_models:
                    return m
        raise RuntimeError(f"All models have failed: {candidates}")

_current_state: ContextVar[ModelState | None] = ContextVar(
    "kairos_model_state",
    default=None,
)


def _get_default_state() -> ModelState:
    state = _current_state.get()
    if state is None:
        state = ModelState()
        _current_state.set(state)
    return state


def configure_state(state: ModelState | None) -> None:
    """Set the active ModelState for the current context."""
    _current_state.set(state)


def reset_state() -> None:
    """Clear the cached ModelState and restore lazy creation."""
    _current_state.set(None)


# Static constants (no dependency on ModelState instance)
PRIORITY = [m for m in [DEFAULT_MODEL, SECONDARY_MODEL] if m]
FALLBACK_MODEL = DEFAULT_MODEL


def _resolve_state(state: ModelState | None = None) -> ModelState:
    """Resolve ModelState: explicit param, then container."""
    if state is not None:
        return state
    return _get_default_state()


# Convenience wrappers â€” accept optional state param for DI
def is_model_failed(model: str, state: ModelState | None = None) -> bool:
    return _resolve_state(state).is_model_failed(model)


def mark_model_failed(model: str, state: ModelState | None = None) -> None:
    _resolve_state(state).mark_model_failed(model)


def clear_failed_models(state: ModelState | None = None) -> None:
    _resolve_state(state).clear_failed_models()


def get_cached_models_safe(state: ModelState | None = None) -> Any:
    return _resolve_state(state).get_cached_models_safe()


def get_verified_models_safe(state: ModelState | None = None) -> Any:
    """Backward-compatible alias for the verified-model cache."""
    from src.llm.model_registry import get_verified_models
    return get_verified_models()


def set_cached_models(value: Any, state: ModelState | None = None) -> None:
    _resolve_state(state).set_cached_models(value)


def _switch_model(model: str, state: ModelState | None = None) -> str:
    return _resolve_state(state).switch_model(model)


__all__ = [
    "ModelState",
    "PRIORITY", "FALLBACK_MODEL",
    "is_model_failed", "mark_model_failed", "clear_failed_models",
    "get_cached_models_safe", "get_verified_models_safe", "set_cached_models",
    "_switch_model",
]


