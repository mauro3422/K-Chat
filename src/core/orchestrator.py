from __future__ import annotations

import logging
import json
import uuid
from datetime import datetime
from collections.abc import Callable, AsyncGenerator
from typing import Any, TYPE_CHECKING

from src.context import build_system_prompt
from src.tools.runner import run_parallel_tools
from src.core.tool_loop import run_tool_loop_streaming, run_tool_loop_sync
from src.memory.types import DebugInfo
from src.memory.repos import Repositories, get_repos
from src.core.orchestrator_contract import (
    OrchestratorDeps, LLMDeps, ToolDeps, StorageDeps, RequestStateDeps,
)
from src.tools.registry import ToolRegistry
import src.tools as tools
from src.llm.selector import get_default_model
import src.llm.client as llm_client
from src.core.history_contract import HistoryMessage

from src.core.services.history_service import HistoryService
from src.core.services.llm_service import LLMService
from src.core.services.tool_execution_service import ToolExecutionService
from src.core.services.telemetry_service import TelemetryService

if TYPE_CHECKING:
    from src.core.services.protocols import (
        HistoryServiceProtocol,
        LLMServiceProtocol,
        ToolExecutionServiceProtocol,
        TelemetryServiceProtocol,
    )

logger: logging.Logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    return str(uuid.uuid4())


def _msg_snapshot(m: Any) -> dict[str, str]:
    if isinstance(m, dict):
        return {"role": m["role"], "content": (m.get("content") or "")[:500]}
    return {"role": m.role, "content": (m.content or "")[:500]}


def _save_debug_info(debug: DebugInfo | None, history: list[dict[str, Any]], phases_output: list[dict[str, Any]] | None) -> None:
    if debug is not None:
        debug.history_before = [_msg_snapshot(m) for m in history]
        debug.phases = json.dumps(phases_output) if phases_output else "[]"


async def chat_stream(
    message_user: str,
    history: list[dict[str, Any]],
    model: str | None = None,
    session_id: str | None = None,
    tagged: bool = False,
    debug: DebugInfo | None = None,
    phases_output: list[dict[str, Any]] | None = None,
    streaming: bool = True,
    compress_fn: Callable[[list[dict[str, Any]], str], None] | None = None,
    should_compress_fn: Callable[[list[dict[str, Any]]], bool] | None = None,
    repos: 'Repositories | None' = None,
    default_model_fn: Callable[[], str] | None = None,
    llm_chat_fn: Callable[..., Any] | None = None,
    llm_chat_stream_fn: Callable[..., Any] | None = None,
    deps: OrchestratorDeps | None = None,
    llm: LLMDeps | None = None,
    tools: ToolDeps | None = None,
    storage: StorageDeps | None = None,
    state: RequestStateDeps | None = None,
) -> AsyncGenerator[Any, None]:
    """Same as chat() but yields tokens. history must be a mutable list."""
    _deps = deps or OrchestratorDeps()
    if llm is not None:
        _deps.llm = llm
    if tools is not None:
        _deps.tools = tools
    if storage is not None:
        _deps.storage = storage
    if state is not None:
        _deps.state = state
    # Backward-compat: positional/keyword params override deps defaults
    if repos is not None:
        _deps.repos = repos
    if default_model_fn is not None:
        _deps.default_model_fn = default_model_fn
    if llm_chat_fn is not None:
        _deps.llm_chat_fn = llm_chat_fn
    if llm_chat_stream_fn is not None:
        _deps.llm_chat_stream_fn = llm_chat_stream_fn
    if compress_fn is not None:
        _deps.compress_fn = compress_fn
    if should_compress_fn is not None:
        _deps.should_compress_fn = should_compress_fn
    if session_id is not None:
        _deps.session_id = session_id
    if tagged:
        _deps.tagged = tagged
    if debug is not None:
        _deps.debug = debug
    if phases_output is not None:
        _deps.phases_output = phases_output
    if not streaming:
        _deps.streaming = streaming

    # Initialize services if not provided
    if _deps.repos is None:
        _deps.repos = get_repos()

    if _deps.history_service is None:
        _deps.history_service = HistoryService(repos=_deps.repos)

    if _deps.telemetry_service is None:
        _deps.telemetry_service = TelemetryService()

    if _deps.llm_service is None:
        _deps.llm_service = LLMService(
            chat_fn=_deps.llm_chat_fn,
            chat_stream_fn=_deps.llm_chat_stream_fn,
            default_model_fn=_deps.default_model_fn,
            telemetry_service=_deps.telemetry_service
        )

    if _deps.tool_service is None:
        _deps.tool_service = ToolExecutionService(tool_registry=_deps.tool_registry)

    if model is None:
        model = _deps.llm_service.get_default_model()

    if _deps.phases_output is not None:
        _deps.phases_output[:] = []

    if _deps.debug is not None:
        _deps.debug.model = model
        _deps.debug.session_id = _deps.session_id or ""
        _deps.debug.reasoning = ""
        _deps.debug.tool_calls = []
        _deps.debug.history_before = []
        _deps.debug.system_prompt = ""

    if not history:
        tool_defs = (_deps.tool_service.tool_registry.definitions
                     if _deps.tool_service and _deps.tool_service.tool_registry else None)
        sp = _deps.history_service.get_system_prompt(model, tool_definitions=tool_defs)
        history.append(HistoryMessage(
            role=sp["role"],
            content=sp["content"],
            created_at=datetime.now().isoformat()
        ))

    if _deps.debug is not None:
        _deps.debug.system_prompt = getattr(history[0], "content", "") or ""

    history.append(HistoryMessage(
        role="user",
        content=message_user,
        created_at=datetime.now().isoformat()
    ))

    if _deps.debug is not None:
        _deps.debug.history_before = [_msg_snapshot(m) for m in history]

    # Execute tool loop via ToolExecutionService
    async for event in _deps.tool_service.execute(
        history, model, _deps.session_id, _deps.tagged, _deps.debug, _deps.phases_output,
        streaming=_deps.streaming,
        repos=_deps.repos,
        llm_chat_fn=_deps.llm_service._chat_fn,
        llm_chat_stream_fn=_deps.llm_service._chat_stream_fn,
    ):
        yield event

    _save_debug_info(_deps.debug, history, _deps.phases_output)

    if _deps.background_tasks:
        _deps.background_tasks.add_task(
            _deps.history_service.compress_if_needed,
            history, model, _deps.compress_fn, _deps.should_compress_fn
        )
    else:
        await _deps.history_service.compress_if_needed(history, model, _deps.compress_fn, _deps.should_compress_fn)

