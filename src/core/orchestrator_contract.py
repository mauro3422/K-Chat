"""Contracts for orchestrator dependency injection.

Split into focused dependency groups:
- ``LLMDeps``       — model selection, client functions, telemetry
- ``ToolDeps``      — tool registry, execution service
- ``StorageDeps``   — repositories, history service, compression
- ``RequestStateDeps`` — per-request state (session, debug, background tasks)

``OrchestratorDeps`` remains as a backward-compatible facade that composes
all four groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from src.memory.repos import Repositories
from src.tools.registry import ToolRegistryProtocol
from src.core.debug_info import DebugInfo

if TYPE_CHECKING:
    from src.core.services.protocols import (
        HistoryServiceProtocol,
        LLMServiceProtocol,
        RetrievalServiceProtocol,
        ToolExecutionServiceProtocol,
        TelemetryServiceProtocol,
    )


# ── Focused dependency groups ──────────────────────────────────────────────


@dataclass(slots=True)
class LLMDeps:
    """LLM-related dependencies: model selection, client functions, telemetry."""
    default_model_fn: Callable[[], str] | None = None
    llm_chat_fn: Callable[..., Any] | None = None
    llm_chat_stream_fn: Callable[..., Any] | None = None
    llm_service: LLMServiceProtocol | None = None
    telemetry_service: TelemetryServiceProtocol | None = None


@dataclass(slots=True)
class ToolDeps:
    """Tool-related dependencies: registry and execution service."""
    tool_registry: ToolRegistryProtocol | None = None
    tool_service: ToolExecutionServiceProtocol | None = None


@dataclass(slots=True)
class StorageDeps:
    """Storage/history dependencies: repos, history service, compression, retrieval."""
    repos: Repositories | None = None
    history_service: HistoryServiceProtocol | None = None
    compress_fn: Callable[[list[dict[str, Any]], str], None] | None = None
    should_compress_fn: Callable[[list[dict[str, Any]]], bool] | None = None
    retrieval_service: RetrievalServiceProtocol | None = None


@dataclass(slots=True)
class RequestStateDeps:
    """Per-request state: session metadata, debug info, background tasks."""
    session_id: str | None = None
    tagged: bool = False
    streaming: bool = True
    debug: DebugInfo | None = None
    phases_output: list[dict[str, Any]] = field(default_factory=list)
    background_tasks: Any | None = None


# ── Field → sub-group mapping (used by OrchestratorDeps delegation) ────────

_FIELD_MAP: dict[str, str] = {
    "default_model_fn": "llm",
    "llm_chat_fn": "llm",
    "llm_chat_stream_fn": "llm",
    "llm_service": "llm",
    "telemetry_service": "llm",
    "tool_registry": "tools",
    "tool_service": "tools",
    "repos": "storage",
    "history_service": "storage",
    "compress_fn": "storage",
    "should_compress_fn": "storage",
    "retrieval_service": "storage",
    "session_id": "state",
    "tagged": "state",
    "streaming": "state",
    "debug": "state",
    "phases_output": "state",
    "background_tasks": "state",
}


# ── Backward-compatible facade ─────────────────────────────────────────────


class OrchestratorDeps:
    """Backward-compatible facade that composes the four dependency groups.

    All original fields are accessible as plain attributes (e.g. ``deps.repos``,
    ``deps.session_id``). New code can also access sub-groups directly via
    ``deps.llm``, ``deps.tools``, ``deps.storage``, ``deps.state``.

    Accepts the same keyword arguments as before for full backward compatibility.
    """

    __slots__ = ("llm", "tools", "storage", "state")

    def __init__(self, **kwargs: Any) -> None:
        object.__setattr__(self, "llm", LLMDeps())
        object.__setattr__(self, "tools", ToolDeps())
        object.__setattr__(self, "storage", StorageDeps())
        object.__setattr__(self, "state", RequestStateDeps())
        for k, v in kwargs.items():
            group = _FIELD_MAP.get(k)
            if group:
                setattr(getattr(self, group), k, v)
            else:
                raise TypeError(
                    f"OrchestratorDeps got unexpected keyword argument {k!r}"
                )

    def __getattr__(self, name: str) -> Any:
        group = _FIELD_MAP.get(name)
        if group:
            return getattr(getattr(self, group), name)
        raise AttributeError(f"OrchestratorDeps has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        group = _FIELD_MAP.get(name)
        if group:
            setattr(getattr(self, group), name, value)
        else:
            super().__setattr__(name, value)
