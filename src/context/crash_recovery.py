"""Crash recovery helpers for system prompt assembly."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.paths import CONTEXT_DIR

logger = logging.getLogger(__name__)

ERROR_CONTEXT_PATH = Path(CONTEXT_DIR) / ".kairos" / "error_context.md"
CRASH_COUNTER_PATH = Path(CONTEXT_DIR) / ".kairos" / "crash_counter"


def _check_crash_loop() -> bool:
    """Check if we're in a crash loop (>3 crashes in 5 min)."""
    now = time.time()

    crashes: list[float] = []
    if CRASH_COUNTER_PATH.exists():
        try:
            raw = CRASH_COUNTER_PATH.read_text().strip()
            for line in raw.split("\n"):
                if line.strip():
                    crashes.append(float(line.strip()))
        except Exception:
            crashes = []

    crashes = [t for t in crashes if now - t < 300]
    crashes.append(now)

    CRASH_COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    CRASH_COUNTER_PATH.write_text("\n".join(str(t) for t in crashes))

    return len(crashes) >= 3


def reset_crash_counter() -> None:
    """Reset the crash counter on clean startup."""
    if CRASH_COUNTER_PATH.exists():
        CRASH_COUNTER_PATH.unlink(missing_ok=True)


def load_error_context() -> str:
    """Read and consume the watchdog's crash report, if present."""
    if _check_crash_loop():
        logger.warning("Crash loop detected (>3 crashes in 5 min) — entering safe mode")
        return (
            "\n\n---\n"
            "## ⚠️ CRASH LOOP DETECTED — Entering safe mode\n\n"
            "Multiple crashes detected in the last 5 minutes. "
            "Do NOT edit any files. Only read and analyze.\n"
            "---\n"
        )

    if not ERROR_CONTEXT_PATH.exists():
        return ""

    try:
        content = ERROR_CONTEXT_PATH.read_text(encoding="utf-8").strip()
        if not content:
            return ""

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
