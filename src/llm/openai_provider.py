import logging
import os
from collections.abc import Generator
from typing import Any
import httpx
from openai import OpenAI
from config import OPENCODE_ZEN_API_KEY

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = os.environ.get("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen/v1")


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        base_url = base_url or _DEFAULT_BASE_URL
        self.client = OpenAI(
            api_key=api_key or OPENCODE_ZEN_API_KEY,
            base_url=base_url,
            timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
        )

    def chat(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Any:
        return self.client.chat.completions.create(model=model, messages=messages, **kwargs)  # type: ignore[arg-type]

    def chat_stream(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Generator[Any, None, None]:
        return self.client.chat.completions.create(model=model, messages=messages, stream=True, **kwargs)  # type: ignore[arg-type]

    def list_models(self) -> list[Any]:
        return list(self.client.models.list())
