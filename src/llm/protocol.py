from __future__ import annotations
from collections.abc import Generator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    def chat(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Any: ...
    def chat_stream(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Generator[Any, None, None]: ...
    def list_models(self) -> list[Any]: ...
