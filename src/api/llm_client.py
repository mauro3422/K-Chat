"""LLM client and model discovery facade."""

from src.llm.selector import get_default_model
from src.llm.discovery import get_verified_models
from src.llm.model_state import get_verified_models_safe, PRIORITY, FALLBACK_MODEL
from src.llm.model_registry import get_model_registry, ensure_registry_refreshed
from src.llm.rate_limit_state import get_rate_limit_store
from src.llm.client import chat_stream as llm_chat_stream, chat as llm_chat

__all__ = [
    "get_default_model",
    "get_verified_models",
    "get_verified_models_safe",
    "get_model_registry",
    "ensure_registry_refreshed",
    "get_rate_limit_store",
    "PRIORITY",
    "FALLBACK_MODEL",
    "llm_chat_stream",
    "llm_chat",
]
