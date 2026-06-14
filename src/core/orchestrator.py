import logging
import json
import uuid
from collections.abc import Callable, Generator
from typing import Any

from src.context import build_system_prompt
from src.tools.runner import run_parallel_tools
from src.core.tool_loop import run_tool_loop_streaming, run_tool_loop_sync
from src.core.debug_info import DebugInfo
from src.memory.repos import Repositories
from src.core.orchestrator_contract import OrchestratorDeps
from src.tools.registry import ToolRegistry
import src.tools as tools

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


def _compress_if_needed(
    history: list[dict[str, Any]],
    model: str,
    compress_fn: Callable[[list[dict[str, Any]], str], None] | None = None,
    should_compress_fn: Callable[[list[dict[str, Any]]], bool] | None = None,
) -> None:
    _should = should_compress_fn or (lambda h: False)
    _compress = compress_fn or (lambda h, m: None)
    if _should(history):
        try:
            _compress(history, model)
        except Exception as e:
            logger.warning("compress_history failed, history not compressed: %s", e)


def _get_tool_registry(deps: OrchestratorDeps) -> ToolRegistry:
    """Get tool registry from deps or fall back to default."""
    if deps.tool_registry is not None:
        return deps.tool_registry
    return get_default_registry()


def get_default_registry() -> ToolRegistry:
    """Get default tool registry (imported from tools package)."""
    return tools.get_default_registry()


def chat_stream(
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
) -> Generator[Any, None, None]:
    """Same as chat() but yields tokens. history must be a mutable list."""
    _deps = deps or OrchestratorDeps(
        repos=repos,
        default_model_fn=default_model_fn,
        llm_chat_fn=llm_chat_fn,
        llm_chat_stream_fn=llm_chat_stream_fn,
        compress_fn=compress_fn,
        should_compress_fn=should_compress_fn,
    )
    if _deps.repos is None:
        from src.memory.repos import get_repos as _get_repos
        _deps.repos = _get_repos()


    # Lazy init tool registry if not injected
    tool_registry = _get_tool_registry(_deps)

    if model is None:
        if _deps.default_model_fn is None:
            from src.llm.selector import get_default_model as _get_default_model
            _deps.default_model_fn = _get_default_model
        model = _deps.default_model_fn()

    if _deps.llm_chat_fn is None or _deps.llm_chat_stream_fn is None:
        import src.llm.client as _llm_client
        if _deps.llm_chat_fn is None:
            _deps.llm_chat_fn = lambda *a, **kw: _llm_client.chat(*a, **kw)
        if _deps.llm_chat_stream_fn is None:
            _deps.llm_chat_stream_fn = lambda *a, **kw: _llm_client.chat_stream(*a, **kw)

    if phases_output is not None:
        phases_output[:] = []

    if debug is not None:
        debug.model = model
        debug.session_id = session_id or ""
        debug.reasoning = ""
        debug.tool_calls = []
        debug.history_before = []
        debug.system_prompt = ""

    if not history:
        history.append(build_system_prompt(model))

    if debug is not None:
        debug.system_prompt = history[0]["content"]

    history.append({"role": "user", "content": message_user})

    if debug is not None:
        debug.history_before = [_msg_snapshot(m) for m in history]

    used_tools: list[str] = []
    tool_detail: list[dict[str, Any]] = []

    loop_fn = run_tool_loop_streaming if streaming else run_tool_loop_sync
    for event in loop_fn(
        history, model, session_id, tagged, debug, phases_output,
        used_tools, tool_detail, run_parallel_tools, tool_registry.tool_map,
        repos=_deps.repos,
        llm_chat_fn=_deps.llm_chat_fn,
        llm_chat_stream_fn=_deps.llm_chat_stream_fn,
        tool_defs=tool_registry.tools_openai,
    ):
        yield event

    _save_debug_info(debug, history, phases_output)
    _compress_if_needed(history, model, _deps.compress_fn, _deps.should_compress_fn)
