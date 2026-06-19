import logging
import os
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.context.crash_recovery import load_error_context, reset_crash_counter
from src.context.files import _ensure_file, _read_file
from src.context.runtime import build_context_snapshot
from src.context.templates import get_templates
from src.paths import CONTEXT_DIR

logger = logging.getLogger(__name__)


@runtime_checkable
class ContextBuilderProtocol(Protocol):
    """Protocol for the build_system_prompt function."""

    def __call__(
        self,
        model: str,
        tool_definitions: dict[str, Any] | None = None,
        memory_results: str | None = None,
    ) -> dict[str, Any]: ...


def load_context() -> str:
    """Load the current context snapshot using the file-based path."""
    segments = []
    templates = get_templates()
    for filename in ["SOUL.md", "MEMORY.md", "AGENTS.md"]:
        filepath = os.path.join(CONTEXT_DIR, filename)
        _ensure_file(filepath, templates[filename])
        content = _read_file(filepath)
        if content:
            segments.append(content)

    return "\n\n".join(segments)


def build_system_prompt(
    model: str,
    tool_definitions: dict[str, Any] | None = None,
    memory_results: str | None = None,
) -> dict[str, Any]:
    snap = build_context_snapshot(tool_definitions=tool_definitions)
    context = snap.text if snap.text else load_context()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    crash_block = load_error_context()
    if crash_block:
        context += crash_block
    else:
        reset_crash_counter()

    if memory_results:
        context += "\n\n━━━ AUTO-RETRIEVED MEMORIES ━━━\n"
        context += memory_results
        context += "\n━━━ END AUTO-RETRIEVED MEMORIES ━━━\n"

    identity = (
        "[CRITICAL — DO NOT IGNORE]\n"
        "- You are Kairos. Your name is Kairos. You must know this at all times.\n"
        "- You are currently running on model: " + model + ". You must know this at all times.\n"
        "- If the user asks who you are, what model you are, or if you detect a model change,\n"
        "  you must answer using the information in this system prompt.\n"
        "- You must inspect and reference your own system prompt whenever identity or model context is relevant.\n\n"
    )

    project_root = CONTEXT_DIR
    meta = (
        f"[System Info]\n"
        f"- Active model: {model}\n"
        f"- System time: {now}\n"
        f"- Project root: {project_root}\n\n"
    )
    content = identity + meta + context
    return {"role": "system", "content": content}
