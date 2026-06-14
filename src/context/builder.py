import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.paths import CONTEXT_DIR
from src.context.templates import TEMPLATES
from src.context.files import _ensure_file, _read_file
from src.context.runtime import build_context_snapshot

logger = logging.getLogger(__name__)

# ═══ CRASH RECOVERY ═══════════════════════════════════════════════════
ERROR_CONTEXT_PATH = Path(CONTEXT_DIR) / ".kairos" / "error_context.md"
"""If the watchdog detected a crash, this file contains the error context."""


def _load_error_context() -> str:
    """Read and consume the watchdog's crash report, if present.

    Returns a formatted block to inject into the system prompt,
    or empty string if no crash context exists.
    """
    if not ERROR_CONTEXT_PATH.exists():
        return ""

    try:
        content = ERROR_CONTEXT_PATH.read_text(encoding="utf-8").strip()
        if not content:
            return ""

        # Read and immediately delete to avoid re-injection
        ERROR_CONTEXT_PATH.unlink(missing_ok=True)

        logger.info("Crash recovery context loaded from %s (%d chars)", ERROR_CONTEXT_PATH, len(content))
        return (
            "\n\n---\n"
            "## ⚠️ CRASH RECOVERY — Auto-detected by Watchdog\n\n"
            "The server crashed since our last conversation. "
            "The watchdog captured the error context below. "
            "Review it and fix the issue.\n\n"
            + content +
            "\n---\n"
        )
    except Exception as e:
        logger.warning("Failed to read error context: %s", e)
        return ""


def load_context() -> str:
    segments = []
    for filename in ["SOUL.md", "MEMORY.md", "AGENTS.md"]:
        filepath = os.path.join(CONTEXT_DIR, filename)
        _ensure_file(filepath, TEMPLATES[filename])
        content = _read_file(filepath)
        if content:
            segments.append(content)

    return "\n\n".join(segments)


def build_system_prompt(model: str) -> dict[str, Any]:
    snap = build_context_snapshot()
    context = snap.text if snap.text else load_context()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # ── Crash recovery block ────────────────────────────────────────
    crash_block = _load_error_context()
    if crash_block:
        context += crash_block

    # Identity and model block is placed FIRST so the LLM cannot miss it
    identity = (
        "[CRITICAL — DO NOT IGNORE]\n"
        "- You are Kairos. Your name is Kairos. You must know this at all times.\n"
        "- You are currently running on model: " + model + ". You must know this at all times.\n"
        "- If the user asks who you are, what model you are, or if you detect a model change,\n"
        "  you must answer using the information in this system prompt.\n"
        "- You must inspect and reference your own system prompt whenever identity or model context is relevant.\n\n"
    )

    PROJECT_ROOT = CONTEXT_DIR
    meta = (
        f"[System Info]\n"
        f"- Active model: {model}\n"
        f"- System time: {now}\n"
        f"- Project root: {PROJECT_ROOT}\n\n"
    )
    content = identity + meta + context
    return {"role": "system", "content": content}
