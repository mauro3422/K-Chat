"""Contracts for orchestrator dependency injection."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

from src.memory.repos import Repositories
from src.tools.registry import ToolRegistry
from src.core.debug_info import DebugInfo

# Type hinting for services to avoid circular imports if any, 
# although we'll use proper imports here as they are in a sub-package.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.core.services.history_service import HistoryService
    from src.core.services.llm_service import LLMService
    from src.core.services.tool_execution_service import ToolExecutionService
    from src.core.services.telemetry_service import TelemetryService

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

    # --- NEW: Service-oriented architecture ---
    history_service: HistoryService | None = None
    llm_service: LLMService | None = None
    tool_service: ToolExecutionService | None = None
    telemetry_service: TelemetryService | None = None

    # --- Per-request state (extracted from chat_stream positional params) ---
    session_id: str | None = None
    tagged: bool = False
    streaming: bool = True
    debug: DebugInfo | None = None
    phases_output: list[dict[str, Any]] = field(default_factory=list)
    background_tasks: Any | None = None
