import logging
import json
import uuid
from collections.abc import Generator
from typing import Any

from src.llm import get_default_model
from src.context import build_system_prompt
from src.compressor import compress_history, should_compress
from src.tools.runner import run_parallel_tools
from src.core.tool_loop import run_tool_loop_streaming, run_tool_loop_sync
from src.core import _deps

logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    return str(uuid.uuid4())


def _msg_snapshot(m: Any) -> dict[str, str]:
    if isinstance(m, dict):
        return {"role": m["role"], "content": (m.get("content") or "")[:500]}
    return {"role": m.role, "content": (m.content or "")[:500]}


def _save_debug_info(debug: dict[str, Any] | None, history: list[dict[str, Any]], phases_output: list[dict[str, Any]] | None) -> None:
    if debug is not None:
        debug["history_before"] = [_msg_snapshot(m) for m in history]
        debug["phases"] = json.dumps(phases_output) if phases_output else "[]"


def _compress_if_needed(history: list[dict[str, Any]], model: str) -> None:
    if should_compress(history):
        try:
            compress_history(history, model)
        except Exception as e:
            logger.warning("compress_history failed, history not compressed: %s", e)


def chat_stream(
    message_user: str,
    history: list[dict[str, Any]],
    model: str | None = None,
    session_id: str | None = None,
    tagged: bool = False,
    debug: dict[str, Any] | None = None,
    phases_output: list[dict[str, Any]] | None = None,
    streaming: bool = True
) -> Generator[Any, None, None]:
    """Same as chat() but yields tokens. history must be a mutable list."""
    if model is None:
        model = get_default_model()

    if phases_output is not None:
        phases_output[:] = []

    if debug is not None:
        debug.clear()
        debug["model"] = model
        debug["session_id"] = session_id
        debug["reasoning"] = ""
        debug["tool_calls"] = []
        debug["history_before"] = []
        debug["system_prompt"] = ""

    if not history:
        history.append(build_system_prompt(model))

    if debug is not None:
        debug["system_prompt"] = history[0]["content"]

    history.append({"role": "user", "content": message_user})

    if debug is not None:
        debug["history_before"] = [_msg_snapshot(m) for m in history]

    used_tools = []
    tool_detail = []

    loop_fn = run_tool_loop_streaming if streaming else run_tool_loop_sync
    for event in loop_fn(
        history, model, session_id, tagged, debug, phases_output,
        used_tools, tool_detail, run_parallel_tools, _deps.TOOL_MAP
    ):
        yield event

    _save_debug_info(debug, history, phases_output)
    _compress_if_needed(history, model)
