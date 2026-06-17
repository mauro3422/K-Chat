from __future__ import annotations

from typing import Any, AsyncGenerator, Callable, Protocol, runtime_checkable


class HistoryServiceProtocol(Protocol):
    async def rebuild(self, session_id: str, model: str) -> list[dict[str, Any]]: ...

    def get_system_prompt(self, model: str) -> dict[str, Any]: ...

    async def compress_if_needed(
        self,
        history: list[dict[str, Any]],
        model: str,
        compress_fn: Callable[[list[dict[str, Any]], str], None] | None = None,
        should_compress_fn: Callable[[list[dict[str, Any]]], bool] | None = None,
    ) -> None: ...


class LLMServiceProtocol(Protocol):
    _chat_fn: Callable[..., Any]
    _chat_stream_fn: Callable[..., Any]

    async def chat(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Any: ...

    async def chat_stream(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> AsyncGenerator[Any, None]: ...

    def get_default_model(self) -> str: ...


class ToolExecutionServiceProtocol(Protocol):
    async def execute(
        self,
        history: list[dict[str, Any]],
        model: str,
        session_id: str | None = None,
        tagged: bool = False,
        debug: Any = None,
        phases_output: list[dict[str, Any]] | None = None,
        streaming: bool = True,
        repos: Any = None,
        llm_chat_fn: Callable[..., Any] | None = None,
        llm_chat_stream_fn: Callable[..., Any] | None = None,
    ) -> AsyncGenerator[Any, None]: ...


class TelemetryServiceProtocol(Protocol):
    def log_event(self, event_type: str, data: dict[str, Any]) -> None: ...

    def track_llm_usage(self, model: str, tokens: int, latency: float) -> None: ...

    def track_tool_execution(self, tool_name: str, success: bool, duration: float) -> None: ...


@runtime_checkable
class HybridRetrieverProtocol(Protocol):
    """Protocol for the hybrid retriever (search + close)."""
    async def search(
        self,
        query: str,
        top_k: int = 10,
        source_filter: str | None = None,
        apply_budget: bool = False,
        session_id: str = "",
    ) -> list[Any]: ...

    def close(self) -> None: ...


class RetrievalServiceProtocol(Protocol):
    """Protocol for the auto-retrieval service (orchestrator-level)."""
    async def retrieve_if_allowed(
        self,
        message_user: str,
        session_id: str | None = None,
        config: Any | None = None,
        db_path: str | None = None,
    ) -> str | None: ...
