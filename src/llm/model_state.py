import logging
import threading
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)


class ModelState:
    def __init__(self, priority=None, fallback_model=None):
        self._lock = threading.Lock()
        self._priority = priority or ["deepseek-v4-flash-free", "big-pickle"]
        self._fallback_model = fallback_model or "deepseek-v4-flash-free"
        self._failed_models: set[str] = set()
        self._verified_models: list[str] | None = None
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

    def get_verified_models_safe(self) -> list[str] | None:
        with self._lock:
            return self._verified_models

    def set_verified_models(self, value: list[str] | None) -> None:
        with self._lock:
            self._verified_models = value

    def get_cached_models_safe(self) -> Any:
        with self._lock:
            return self._cached_models

    def set_cached_models(self, value: Any) -> None:
        with self._lock:
            self._cached_models = value

    def switch_model(self, model: str) -> str:
        """Switch to an alternative model. NEVER returns a failed model.

        If model == fallback: scan priority for any non-failed model.
        If model != fallback: try fallback first, then scan priority.
        If all models failed: raise RuntimeError.
        """
        with self._lock:
            if model == self._fallback_model or model not in self._priority:
                for m in self._priority:
                    if m not in self._failed_models:
                        return m
            else:
                if self._fallback_model not in self._failed_models:
                    return self._fallback_model
                for m in self._priority:
                    if m not in self._failed_models:
                        return m
        raise RuntimeError(f"All models have failed: {self._priority}")


_DEFAULT_STATE = ModelState()

__all__ = [
    "ModelState",
    "PRIORITY", "FALLBACK_MODEL",
    "is_model_failed", "mark_model_failed", "clear_failed_models",
    "get_verified_models_safe", "set_verified_models",
    "get_cached_models_safe", "set_cached_models",
    "_switch_model", "_DEFAULT_STATE",
]

PRIORITY = _DEFAULT_STATE.priority
FALLBACK_MODEL = _DEFAULT_STATE.fallback_model

is_model_failed = _DEFAULT_STATE.is_model_failed
mark_model_failed = _DEFAULT_STATE.mark_model_failed
clear_failed_models = _DEFAULT_STATE.clear_failed_models
get_verified_models_safe = _DEFAULT_STATE.get_verified_models_safe
set_verified_models = _DEFAULT_STATE.set_verified_models
get_cached_models_safe = _DEFAULT_STATE.get_cached_models_safe
set_cached_models = _DEFAULT_STATE.set_cached_models
_switch_model = _DEFAULT_STATE.switch_model
