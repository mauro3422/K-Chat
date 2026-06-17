"""Orchestrator facade — wraps core orchestrator for entry points."""

from src.core.orchestrator import (
    chat_stream,
    generate_session_id,
)
from src.core.orchestrator_contract import OrchestratorDeps
from src.core.history_rebuilder import rebuild_history
from src.core.history_contract import HistoryRebuildDeps
from src.core.history_ui import filter_messages_for_ui, match_tools_to_msgs
from src.core.services.history_service import HistoryService
from src.core.services.history_service import HistoryServiceProtocol
from src.core.services.llm_service import LLMService
from src.core.services.llm_service import LLMServiceProtocol
from src.core.services.tool_execution_service import ToolExecutionService
from src.core.services.tool_execution_service import ToolExecutionServiceProtocol
from src.core.services.telemetry_service import TelemetryService
from src.core.services.telemetry_service import TelemetryServiceProtocol

__all__ = [
    "chat_stream",
    "generate_session_id",
    "OrchestratorDeps",
    "rebuild_history",
    "HistoryRebuildDeps",
    "filter_messages_for_ui",
    "match_tools_to_msgs",
    "HistoryService",
    "HistoryServiceProtocol",
    "LLMService",
    "LLMServiceProtocol",
    "ToolExecutionService",
    "ToolExecutionServiceProtocol",
    "TelemetryService",
    "TelemetryServiceProtocol",
]
