from __future__ import annotations
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable, Union


@dataclass
class UnifiedRequest:
    messages: list[dict[str, Any]]
    model: str
    tools: list[dict[str, Any]] | None = None
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class UnifiedToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class UnifiedToolCallDelta:
    index: int
    id: str | None
    name: str | None
    arguments: str | None
    status: str  # "start", "partial", "complete"


@dataclass
class FinishInfo:
    finish_reason: str
    usage: Usage | None = None


@dataclass
class UnifiedResponse:
    content: str | None
    reasoning: str | None
    tool_calls: list[UnifiedToolCall] | None
    usage: Usage | None
    finish_reason: str
    model: str


UnifiedStreamEvent = Union[
    tuple[str, str],  # ("content", "text") or ("reasoning", "text")
    tuple[str, UnifiedToolCallDelta],  # ("tool_call", UnifiedToolCallDelta)
    tuple[str, Usage],  # ("usage", Usage)
    tuple[str, FinishInfo],  # ("done", FinishInfo)
]


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def supports_streaming(self) -> bool: ...

    @property
    def supports_tools(self) -> bool: ...

    @property
    def supports_reasoning(self) -> bool: ...

    def chat(self, request: UnifiedRequest) -> UnifiedResponse: ...

    def chat_stream(self, request: UnifiedRequest) -> Generator[UnifiedStreamEvent, None, None]: ...

    def list_models(self) -> list[str]: ...
