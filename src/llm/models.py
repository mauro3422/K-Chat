import logging
import time
from openai import OpenAI
from config import OPENCODE_ZEN_API_KEY
from src.context import build_system_prompt

logger = logging.getLogger(__name__)

_MAX_RETRIES = 1
_RETRY_DELAY = 0.5

client = OpenAI(
    api_key=OPENCODE_ZEN_API_KEY,
    base_url="https://opencode.ai/zen/v1"
)

PRIORITY = ["big-pickle", "deepseek-v4-flash-free"]
FALLBACK_MODEL = "deepseek-v4-flash-free"

_cached_models = None
_verified_models = None
_failed_models = set()

def _api_call(**kwargs):
    """Wrapper con retry exponencial sobre client.chat.completions.create."""
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.debug("Retry %d/%d para %s en %.1fs: %s", attempt + 1, _MAX_RETRIES, kwargs.get("model"), delay, e)
                time.sleep(delay)
    raise last_error

def _switch_model(model: str) -> str:
    """Devuelve el modelo alternativo cuando el actual falló."""
    return FALLBACK_MODEL if model != FALLBACK_MODEL else "big-pickle"

def _update_system_prompt(messages: list, model: str) -> None:
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0] = build_system_prompt(model)
