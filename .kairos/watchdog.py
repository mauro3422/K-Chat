#!/usr/bin/env python3
"""K-Chat Watchdog — self-healing crash recovery daemon.

Monitors the web server health endpoint. If the server is unreachable
(indicating a crash from a bad edit or runtime error), this watchdog:

1. Captures the git diff and last commits
2. Writes ``.kairos/error_context.md`` with full crash context
3. Restarts the systemd service

The error_context.md is read by ``src/context/builder.py`` on next boot,
so Kairos sees exactly what went wrong and can self-heal.

Usage:
    python .kairos/watchdog.py                  # foreground
    systemctl --user start k-chat-watchdog       # as systemd service

Configuration (environment variables):
    WATCHDOG_INTERVAL    — Health check interval in seconds (default: 5)
    WATCHDOG_URL         — Health endpoint URL (default: http://127.0.0.1:8000/health)
    K_CHAT_PROJECT       — Project root path (default: auto-detected)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
)
logger = logging.getLogger("watchdog")

# ─── Config ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ERROR_CONTEXT_FILE = PROJECT_ROOT / ".kairos" / "error_context.md"
HEALTH_URL = os.getenv("WATCHDOG_URL", "http://127.0.0.1:8000/health")
CHECK_INTERVAL = int(os.getenv("WATCHDOG_INTERVAL", "15"))
# Allow up to 3 minutes for first-time startup (embedding model download
# from HuggingFace can take 60-120 seconds on the first run).
STARTUP_GRACE = int(os.getenv("WATCHDOG_STARTUP_GRACE", "180"))
# Require 12 consecutive failures (3 min at 15s intervals) before triggering
# recovery. Tools like recall_memories & web_search can block the main thread
# for 60-120s during execution — shorter windows cause false-positive kills.
REQUIRED_FAILURES = int(os.getenv("WATCHDOG_REQUIRED_FAILURES", "12"))


def _git_log(count: int = 5) -> str:
    """Get last N commits."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{count}", "--oneline"],
            capture_output=True, text=True, timeout=10,
            cwd=PROJECT_ROOT,
        )
        return result.stdout
    except Exception as e:
        return f"[git log error: {e}]"


def _git_diff() -> str:
    """Get uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True, timeout=10,
            cwd=PROJECT_ROOT,
        )
        output = result.stdout
        # Truncate to avoid massive files
        if len(output) > 5000:
            output = output[:4997] + "..."
        return output
    except Exception as e:
        return f"[git diff error: {e}]"


def _git_diff_cached() -> str:
    """Get staged but not committed changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, timeout=10,
            cwd=PROJECT_ROOT,
        )
        return result.stdout[:2000]
    except Exception as e:
        return f"[git diff-cached error: {e}]"


def _write_error_context(error_type: str, detail: str) -> None:
    """Write crash context to error_context.md for injection into system prompt."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"""# ⚡ CRASH RECOVERY — {error_type}
Detected: {now}

---

## What Happened
{detail}

## Last Commits
{_git_log(5)}

## Uncommitted Changes (likely culprit)
```diff
{_git_diff()}
```

## Staged Changes
```
{_git_diff_cached()}
```

---

*This file was written by the watchdog on crash detection.
It will be read by the system prompt builder on next startup.
Kairos will see this and can auto-fix the issue.*
"""
    try:
        ERROR_CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
        ERROR_CONTEXT_FILE.write_text(content)
        logger.info("Wrote error context to %s", ERROR_CONTEXT_FILE)
    except Exception as e:
        logger.error("Failed to write error context: %s", e)


def _restart_service() -> None:
    """Restart the k-chat systemd service."""
    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "k-chat"],
            capture_output=True, text=True, timeout=30,
        )
        logger.info("Restarted k-chat service via systemd")
    except Exception as e:
        logger.error("Failed to restart service: %s", e)
        # Fallback: try pkill
        try:
            subprocess.run(
                ["pkill", "-f", "uvicorn"],
                capture_output=True, timeout=10,
            )
            logger.info("Fallback: killed uvicorn processes")
        except Exception:
            pass


def _health_check() -> bool:
    """Returns True if the server is healthy."""
    try:
        import urllib.request
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _check_bot_alive() -> bool:
    """Check if the Telegram bot process is alive via its PID file.

    Returns True if the PID file exists and the process is running.
    This is a non-critical check — the bot is managed by systemd
    (``Restart=always``), so this just provides visibility.
    """
    pid_file = PROJECT_ROOT / ".kairos" / "telegram_bot.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, IOError):
        return False


def main() -> None:
    logger.info("Watchdog started (interval=%ds, url=%s)", CHECK_INTERVAL, HEALTH_URL)
    logger.info("Project root: %s", PROJECT_ROOT)

    # Grace period for initial startup
    logger.info("Startup grace period: %ds", STARTUP_GRACE)
    time.sleep(STARTUP_GRACE)

    consecutive_failures = 0
    last_healthy = time.time()
    crash_cooldown = 60  # Don't trigger crash recovery more than once per minute
    last_crash_time = 0.0
    bot_status_log = 0  # Only log bot status every N cycles

    while True:
        try:
            # ─── Bot status check (non-critical, periodic) ─────────────
            bot_status_log += 1
            if bot_status_log % 12 == 0:  # ~every 60s (12 × 5s)
                if not _check_bot_alive():
                    logger.warning("Bot PID file not found or process dead "
                                   "(systemd should auto-restart)")
                bot_status_log = 0

            # ─── Web server health check ───────────────────────────────
            healthy = _health_check()

            if healthy:
                if consecutive_failures > 0:
                    logger.info("Server recovered after %d failures", consecutive_failures)
                consecutive_failures = 0
                last_healthy = time.time()
                time.sleep(CHECK_INTERVAL)
                continue

            # ─── Server is DOWN ─────────────────────────────────────────
            consecutive_failures += 1
            now = time.time()

            logger.warning("Health check failed (%d consecutive)", consecutive_failures)

            # Require N consecutive failures to confirm crash (avoid false positives)
            if consecutive_failures < REQUIRED_FAILURES:
                time.sleep(CHECK_INTERVAL)
                continue

            # Check cooldown
            if now - last_crash_time < crash_cooldown:
                logger.info("Crash cooldown active, skipping recovery")
                time.sleep(CHECK_INTERVAL)
                continue

            last_crash_time = now

            # ─── Crash confirmed ────────────────────────────────────────
            uptime = now - last_healthy
            logger.critical("Server CRASHED (was up for %.0fs)", uptime)

            detail = (
                f"Server became unresponsive after {uptime:.0f}s of uptime.\n"
                f"Consecutive health check failures: {consecutive_failures}\n"
                f"This likely means a recent code edit caused a runtime error.\n"
            )
            _write_error_context("SERVER_DOWN", detail)

            # Write cache invalidation marker so runtime.py forces a reload
            invalidate_path = ERROR_CONTEXT_FILE.parent / "invalidate_cache"
            try:
                invalidate_path.write_text(datetime.now().isoformat())
                logger.info("Wrote cache invalidation marker")
            except Exception as e:
                logger.error("Failed to write invalidation marker: %s", e)

            _restart_service()

            # Reset counter and wait for server to come back
            consecutive_failures = 0
            logger.info("Waiting 15s for server to restart...")
            time.sleep(15)

        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user")
            break
        except Exception as e:
            logger.exception("Watchdog error: %s")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
