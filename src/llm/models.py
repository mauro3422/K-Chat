import logging
import os
import threading
import time
from typing import Any
from src.llm.protocol import LLMProvider
from src.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

_models_lock = threading.Lock()

_MAX_RETRIES = 1
_RETRY_DELAY = 0.5


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

PRIORITY = ["big-pickle", "deepseek-v4-flash-free"]
FALLBACK_MODEL = "deepseek-v4-flash-free"

_cached_models = None
_verified_models = None
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


def _api_call(**kwargs: Any) -> Any:
    """Wrapper over provider with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return _get_provider().chat(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.debug("Retry %d/%d for %s in %.1fs: %s", attempt + 1, _MAX_RETRIES, kwargs.get("model"), delay, e)
                time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected error in _api_call")

def _switch_model(model: str) -> str:
    """Returns the fallback model when the current one failed."""
    if model == FALLBACK_MODEL:
        with _models_lock:
            for m in PRIORITY:
                if m not in _failed_models:
                    return m
        return FALLBACK_MODEL
    return FALLBACK_MODEL
