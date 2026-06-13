"""Contracts for orchestrator dependency injection."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from src.memory.repos import Repositories
from src.tools.registry import ToolRegistry


@dataclass(slots=True)
class OrchestratorDeps:
    """Optional dependency bundle for chat_stream orchestration."""

    repos: Repositories | None = None
    default_model_fn: Callable[[], str] | None = None
    llm_chat_fn: Callable[..., Any] | None = None
    llm_chat_stream_fn: Callable[..., Any] | None = None
    compress_fn: Callable[[list[dict[str, Any]], str], None] | None = None
    should_compress_fn: Callable[[list[dict[str, Any]]], bool] | None = None
    tool_registry: ToolRegistry | None = None  # NEW: injectable tool registry
