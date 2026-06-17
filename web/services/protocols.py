from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Protocol

from src.api.repos import DebugInfo
from web.services.message_persister_contract import MessagePersisterDeps
from web.services.message_renderer_contract import MessageRenderDeps


class StreamGeneratorProtocol(Protocol):
    """Protocol for an async generator function that yields NDJSON stream events."""
    def __call__(self) -> AsyncGenerator[str, None]:
        ...


class MessagePersisterProtocol(Protocol):
    """Protocol for saving assistant messages to persistent storage."""
    async def __call__(
        self,
        session_id: str,
        full_content: str,
        full_reasoning: str,
        phases_output: list[dict[str, Any]],
        debug_info: DebugInfo,
        model: str,
        repos: Any | None = None,
        deps: MessagePersisterDeps | None = None,
    ) -> None:
        ...


class MessageRendererProtocol(Protocol):
    """Protocol for rendering session messages for the UI."""
    async def __call__(
        self,
        session_id: str,
        deps: MessageRenderDeps | None = None,
    ) -> dict:
        ...
