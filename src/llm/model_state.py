import logging
import threading
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)

__all__ = [
    "PRIORITY", "FALLBACK_MODEL",
    "_failed_models",
    "is_model_failed", "mark_model_failed",
    "get_verified_models_safe", "set_verified_models",
    "get_cached_models_safe", "set_cached_models",
    "_switch_model",
]

_models_lock: threading.Lock = threading.Lock()

PRIORITY: list[str] = ["deepseek-v4-flash-free", "big-pickle"]
FALLBACK_MODEL: str = "deepseek-v4-flash-free"

_cached_models: list[Any] | None = None
_verified_models: list[str] | None = None
_failed_models: set[str] = set()


# --- Thread-safe accessors for shared mutable state ---

def is_model_failed(model: str) -> bool:
    with _models_lock:
        return model in _failed_models

def mark_model_failed(model: str) -> None:
    with _models_lock:
        _failed_models.add(model)

def get_verified_models_safe() -> list[str] | None:
    with _models_lock:
        return _verified_models

def set_verified_models(value: list[str] | None) -> None:
    with _models_lock:
        global _verified_models
        _verified_models = value

def get_cached_models_safe() -> Any:
    with _models_lock:
        return _cached_models

def set_cached_models(value: Any) -> None:
    with _models_lock:
        global _cached_models
        _cached_models = value


def _switch_model(model: str) -> str:
    """Returns the fallback model when the current one failed."""
    if model == FALLBACK_MODEL:
        with _models_lock:
            for m in PRIORITY:
                if m not in _failed_models:
                    return m
        return FALLBACK_MODEL
    return FALLBACK_MODEL
