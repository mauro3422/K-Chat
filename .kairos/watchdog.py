#!/usr/bin/env python3
"""K-Chat Watchdog — self-healing crash recovery daemon.

Monitors the web server health endpoint. If the server is unreachable
(indicating a crash from a bad edit or runtime error), this watchdog:

1. Captures the git diff and last commits
2. Writes ``.kairos/error_context.md`` with full crash context
3. Asks the canonical systemd user service to restart
4. Waits for the managed server to pass a health check

Only systemd owns the uvicorn process. The watchdog never spawns or kills
the web server directly, preventing duplicate listeners and restart races.

Usage:
    python .kairos/watchdog.py                  # foreground
    sudo systemctl start kairos                 # recommended — starts watchdog via service

Configuration (environment variables):
    WATCHDOG_INTERVAL    — Health check interval in seconds (default: 15)
    WATCHDOG_URL         — Health endpoint URL (default: http://127.0.0.1:8000/health)
    K_CHAT_PROJECT       — Project root path (default: auto-detected)
"""

from __future__ import annotations

import logging
import os
import subprocess
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
# Allow up to 5 minutes for first-time startup. Model loading can temporarily
# occupy the event loop even after uvicorn binds its port.
STARTUP_GRACE = int(os.getenv("WATCHDOG_STARTUP_GRACE", "300"))
# Require N consecutive failures before triggering recovery.
# Tools like recall_memories & web_search can block the main thread for
# 60-120s — shorter windows cause false-positive kills.
REQUIRED_FAILURES = int(os.getenv("WATCHDOG_REQUIRED_FAILURES", "6"))
# Max retries for restart attempts
MAX_RESTART_RETRIES = 3
# Time to wait for the new server to come up after restart (seconds)
SERVER_STARTUP_TIMEOUT = int(os.getenv("WATCHDOG_STARTUP_TIMEOUT", "300"))

# ─── Helpers ────────────────────────────────────────────────────────────

def _health_check() -> bool:
    """Returns True if the server is healthy."""
    try:
        import urllib.request
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _wait_for_server(timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
    """Poll health endpoint until the server responds or timeout."""
    deadline = time.time() + timeout
    logger.info("Waiting for server to start (timeout=%ds)...", timeout)
    while time.time() < deadline:
        if _health_check():
            logger.info("Server is healthy")
            return True
        time.sleep(2)
    return False


def _managed_service_is_active() -> bool:
    """Return whether systemd still considers the web service active."""
    service = os.getenv("KAIROS_WEB_SERVICE", "k-chat.service").strip()
    if not service:
        return False
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", service],
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


# ─── Git + error context ────────────────────────────────────────────────

def _git_log(count: int = 5) -> str:
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
    try:
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True, timeout=10,
            cwd=PROJECT_ROOT,
        )
        output = result.stdout
        if len(output) > 5000:
            output = output[:4997] + "..."
        return output
    except Exception as e:
        return f"[git diff error: {e}]"


def _git_diff_cached() -> str:
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


def _write_invalidation_marker() -> None:
    invalidate_path = ERROR_CONTEXT_FILE.parent / "invalidate_cache"
    try:
        invalidate_path.write_text(datetime.now().isoformat())
        logger.info("Wrote cache invalidation marker")
    except Exception as e:
        logger.error("Failed to write invalidation marker: %s", e)


# ─── Core restart logic ─────────────────────────────────────────────────

def kill_and_restart() -> bool:
    """Restart the canonical systemd-managed web service."""
    service = os.getenv("KAIROS_WEB_SERVICE", "k-chat.service").strip()
    if not service:
        logger.error("KAIROS_WEB_SERVICE must not be empty")
        return False

    for attempt in range(1, MAX_RESTART_RETRIES + 1):
        logger.info(
            "Restarting systemd user service %s (attempt %d/%d)",
            service,
            attempt,
            MAX_RESTART_RETRIES,
        )
        try:
            result = subprocess.run(
                ["systemctl", "--user", "restart", service],
                capture_output=True,
                text=True,
                timeout=45,
            )
        except Exception as exc:
            logger.error("Could not restart %s: %s", service, exc)
            time.sleep(2)
            continue
        if result.returncode != 0:
            logger.error(
                "systemctl restart failed for %s: %s",
                service,
                result.stderr.strip() or result.stdout.strip(),
            )
            time.sleep(2)
            continue

        if _wait_for_server(timeout=SERVER_STARTUP_TIMEOUT):
            logger.info("Server restarted successfully (attempt %d/%d)", attempt, MAX_RESTART_RETRIES)
            return True

        logger.error("Attempt %d/%d: managed server is not healthy — retrying", attempt, MAX_RESTART_RETRIES)
        time.sleep(2)

    return False


def _check_bot_alive() -> bool:
    """Check if the Telegram bot process is alive via its PID file."""
    pid_file = PROJECT_ROOT / ".kairos" / "telegram_bot.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, IOError):
        return False


# ─── Main loop ──────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 50)
    logger.info("Watchdog started")
    logger.info("  Interval: %ds  Failures required: %d", CHECK_INTERVAL, REQUIRED_FAILURES)
    logger.info("  Health URL: %s", HEALTH_URL)
    logger.info("  Project root: %s", PROJECT_ROOT)
    logger.info("=" * 50)

    # systemd owns startup. A fresh process may be temporarily unresponsive
    # while loading models, so the watchdog observes without racing it.
    if not _health_check():
        logger.info("Managed server is warming up; startup grace is %ds", STARTUP_GRACE)
    else:
        logger.info("Server already running on startup — monitoring")

    consecutive_failures = 0
    last_healthy = time.time()
    crash_cooldown = 60  # Don't trigger recovery more than once per minute
    last_crash_time = 0.0
    bot_status_log = 0

    while True:
        try:
            # ─── Bot status check (non-critical, periodic) ─────────────
            bot_status_log += 1
            if bot_status_log % 12 == 0:  # ~every 180s (12 × 15s)
                if not _check_bot_alive():
                    logger.warning("Bot PID file not found or process dead")
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

            if consecutive_failures < REQUIRED_FAILURES:
                time.sleep(CHECK_INTERVAL)
                continue

            downtime = now - last_healthy
            if _managed_service_is_active() and downtime < STARTUP_GRACE:
                logger.info(
                    "Managed service is active and still inside startup grace "
                    "(%.0fs/%ds); skipping recovery",
                    downtime,
                    STARTUP_GRACE,
                )
                time.sleep(CHECK_INTERVAL)
                continue

            # Cooldown check
            if now - last_crash_time < crash_cooldown:
                logger.info("Crash cooldown active, skipping recovery")
                time.sleep(CHECK_INTERVAL)
                continue

            last_crash_time = now

            # ─── Crash confirmed — recover ─────────────────────────────
            uptime = now - last_healthy
            logger.critical("Server DOWN (was up for %.0fs) — starting recovery", uptime)

            detail = (
                f"Server became unresponsive after {uptime:.0f}s of uptime.\n"
                f"Consecutive health check failures: {consecutive_failures}\n"
                f"This likely means a recent code edit caused a runtime error.\n"
            )
            _write_error_context("SERVER_DOWN", detail)
            _write_invalidation_marker()

            if kill_and_restart():
                logger.info("Recovery successful — server is healthy again")
            else:
                logger.critical("Recovery FAILED after %d attempts — manual intervention needed",
                                MAX_RESTART_RETRIES)
                _write_error_context("RECOVERY_FAILED",
                                     f"Server could not be restarted after {MAX_RESTART_RETRIES} attempts.\n"
                                     f"Check .kairos/error_context.md for details.\n"
                                     f"Manual restart required: sudo systemctl restart kairos")

            # Reset and wait for next cycle
            consecutive_failures = 0
            time.sleep(15)

        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user")
            break
        except Exception as e:
            logger.exception("Watchdog error: %s", e)
            time.sleep(CHECK_INTERVAL)

    logger.info("Watchdog exited; managed web service left untouched")


if __name__ == "__main__":
    main()
