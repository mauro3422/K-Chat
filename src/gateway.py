"""Kairos Gateway — unified launcher for all services.

Usage:
    python -m src.gateway              # start all services
    python -m src.gateway --verbose    # with debug logs in console
    python -m src.gateway --no-web     # skip web dashboard
    python -m src.gateway --no-telegram # skip telegram bot
    python -m src.gateway --no-searxng  # skip SearXNG
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config_loader import DEFAULT_CONFIG

logger = logging.getLogger("gateway")

_services: dict[str, dict[str, Any]] = {}
_shutdown = False
_start_time: float = 0.0

_BANNER_TEMPLATE = (Path(__file__).parent / "gateway_banner.txt").read_text()
BANNER = _BANNER_TEMPLATE.replace("__VERSION__", "0.0.53")

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log_starting(name: str) -> None:
    print(f"  {DIM}{_ts()}{RESET}  {CYAN}▸{RESET} {name} {DIM}starting...{RESET}")


def _log_ok(name: str, detail: str = "") -> None:
    suffix = f"  {DIM}{detail}{RESET}" if detail else ""
    print(f"  {DIM}{_ts()}{RESET}  {GREEN}✓{RESET} {name}{suffix}")


def _log_skip(name: str, reason: str = "") -> None:
    suffix = f"  {DIM}({reason}){RESET}" if reason else ""
    print(f"  {DIM}{_ts()}{RESET}  {YELLOW}○{RESET} {name} {DIM}skipped{RESET}{suffix}")


def _log_fail(name: str, reason: str = "") -> None:
    suffix = f"  {DIM}{reason}{RESET}" if reason else ""
    print(f"  {DIM}{_ts()}{RESET}  {RED}✗{RESET} {name} {DIM}failed{RESET}{suffix}")


def _print_services(services: dict[str, dict[str, Any]], verbose: bool) -> None:
    running = sum(1 for s in services.values() if s.get("running"))
    total = len(services)
    print()
    print(f"  {BOLD}Services{RESET}  {DIM}{running}/{total} active{RESET}")
    print(f"  {DIM}{'─' * 44}{RESET}")
    for name, info in services.items():
        is_running = info.get("running", False)
        detail = info.get("detail", "")
        url = info.get("url", "")
        status = f"{GREEN}●{RESET}" if is_running else f"{RED}✗{RESET}"
        line = f"  {status} {name:<16}"
        if url:
            line += f" {DIM}→{RESET} {url}"
        if detail:
            line += f"  {DIM}{detail}{RESET}"
        print(line)
    print(f"  {DIM}{'─' * 44}{RESET}")
    print()
    if verbose:
        print(f"  {DIM}Verbose mode ON — logs stream below{RESET}")
        print(f"  {DIM}{'─' * 44}{RESET}")
    print(f"  {DIM}SIGUSR1=status  SIGHUP=reload  Ctrl+C=stop{RESET}")
    print()


def _cleanup_orphans() -> None:
    """Kill orphan processes and remove stale PID files from previous sessions."""
    import subprocess as _sp

    stale_pids = [
        (".kairos/telegram_bot.pid", ["python", "-m", "channels.telegram"]),
    ]
    for pid_file, proc_patterns in stale_pids:
        pid_path = Path(pid_file)
        if pid_path.exists():
            try:
                old_pid = int(pid_path.read_text().strip())
                alive = _sp.run(
                    ["kill", "-0", str(old_pid)],
                    capture_output=True, timeout=2,
                )
                if alive.returncode == 0:
                    _sp.run(["kill", str(old_pid)], capture_output=True, timeout=5)
                    time.sleep(0.5)
            except Exception:
                pass
            pid_path.unlink(missing_ok=True)

    for pattern in ["uvicorn web.server:app", "channels.telegram", "searx.webapp"]:
        _sp.run(
            ["pkill", "-f", pattern],
            capture_output=True, timeout=5,
        )
    time.sleep(0.3)
    for port in [8000, 8080]:
        _sp.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, timeout=5)
    time.sleep(0.3)


# ── Service Starters ────────────────────────────────────────────────────

def _start_searxng(verbose: bool) -> bool:
    if not os.environ.get("SEARXNG_AUTO_START", "false").lower() in ("1", "true"):
        return False
    from dependencies import manage as deps
    err = deps.searxng_start()
    if err:
        if verbose:
            logger.warning("SearXNG: %s", err)
        return False
    return True


def _start_web(verbose: bool) -> subprocess.Popen | None:
    host = DEFAULT_CONFIG.host
    port = DEFAULT_CONFIG.port
    cmd = [
        sys.executable, "-m", "uvicorn",
        "web.server:app",
        "--host", host,
        "--port", str(port),
        "--log-level", "warning" if not verbose else "info",
    ]
    env = os.environ.copy()
    env["SEARXNG_AUTO_START"] = "false"
    log_dir = Path(DEFAULT_CONFIG.kairos_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    stderr_log = open(log_dir / "web_server.log", "a")
    kwargs: dict[str, Any] = {
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": stderr_log,
    }
    try:
        return subprocess.Popen(cmd, **kwargs)
    except Exception as e:
        if verbose:
            logger.error("Failed to start web server: %s", e)
        return None


def _start_telegram(verbose: bool) -> subprocess.Popen | None:
    if not DEFAULT_CONFIG.telegram_bot_token:
        return None
    cmd = [sys.executable, "-m", "channels.telegram"]
    log_dir = Path(DEFAULT_CONFIG.kairos_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    stderr_log = open(log_dir / "telegram.log", "a")
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": stderr_log,
    }
    try:
        return subprocess.Popen(cmd, **kwargs)
    except Exception as e:
        if verbose:
            logger.error("Failed to start Telegram bot: %s", e)
        return None


# ── Process Management ──────────────────────────────────────────────────

def _stop_all() -> None:
    global _shutdown
    if _shutdown:
        return
    _shutdown = True

    from src.gateway_log import log_shutdown, log_event
    uptime = time.time() - _start_time

    for name, info in _services.items():
        proc = info.get("process")
        if proc and hasattr(proc, "terminate"):
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            log_shutdown(name, f"uptime={uptime:.0f}s")

    from dependencies import manage as deps
    deps.searxng_stop()
    log_shutdown("gateway", f"total_uptime={uptime:.0f}s")

    print(f"\n  {DIM}{'─' * 44}{RESET}")
    print(f"  {RED}■{RESET} All services stopped  {DIM}({uptime:.0f}s uptime){RESET}")
    print()


def _check_alive() -> str | None:
    for name, info in _services.items():
        proc = info.get("process")
        if proc and hasattr(proc, "poll"):
            code = proc.poll()
            if code is not None:
                return f"{name} (exit code: {code})"
    return None


# ── Health Check ────────────────────────────────────────────────────────

def _health_check() -> dict[str, Any]:
    """Check web server health endpoint."""
    url = f"http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        start = time.time()
        with urllib.request.urlopen(req, timeout=3) as resp:
            latency_ms = (time.time() - start) * 1000
            data = resp.read().decode()
            return {"ok": resp.status == 200, "latency_ms": round(latency_ms, 1), "body": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Signal Handlers ─────────────────────────────────────────────────────

def _handle_sigusr1(signum: int, frame: Any) -> None:
    """SIGUSR1 — dump status to stdout."""
    from src.gateway_log import log_signal
    log_signal("USR1", "status_dump")

    uptime = time.time() - _start_time
    print(f"\n  {BOLD}── Status Dump ──{RESET}")
    print(f"  Uptime: {uptime:.0f}s")
    print(f"  PID: {os.getpid()}")
    for name, info in _services.items():
        proc = info.get("process")
        pid = proc.pid if proc and hasattr(proc, "pid") else None
        running = info.get("running", False)
        status = f"{GREEN}●{RESET}" if running else f"{RED}✗{RESET}"
        print(f"  {status} {name}: PID={pid or 'N/A'}")
    health = _health_check()
    h_status = f"{GREEN}OK{RESET}" if health.get("ok") else f"{RED}FAIL{RESET}"
    h_detail = f" ({health.get('latency_ms', '?')}ms)" if health.get("ok") else f" ({health.get('error', '?')})"
    print(f"  Health: {h_status}{h_detail}")
    print(f"  {BOLD}── End Status ──{RESET}\n")


def _handle_sighup(signum: int, frame: Any) -> None:
    """SIGHUP — reload .env config."""
    from src.gateway_log import log_signal
    from dotenv import load_dotenv
    load_dotenv(override=True)
    log_signal("HUP", "config_reloaded")
    print(f"\n  {DIM}{_ts()}{RESET}  {YELLOW}↻{RESET} Config reloaded (SIGHUP)\n")


def _handle_sigchld(signum: int, frame: Any) -> None:
    """SIGCHLD — a child process changed state. Only log if unexpected."""
    if _shutdown:
        return
    import os as _os
    while True:
        try:
            pid, status = _os.waitpid(-1, _os.WNOHANG)
            if pid == 0:
                break
            exit_code = _os.WEXITSTATUS(status) if _os.WIFEXITED(status) else -1
            for name, info in _services.items():
                proc = info.get("process")
                if proc and hasattr(proc, "pid") and proc.pid == pid:
                    from src.gateway_log import log_crash
                    log_crash(name, f"exit_code={exit_code}", pid=pid)
                    print(f"\n  {DIM}{_ts()}{RESET}  {RED}✗{RESET} {name} died (exit {exit_code})")
                    break
        except ChildProcessError:
            break


# ── Heartbeat ───────────────────────────────────────────────────────────

def _heartbeat_loop(verbose: bool) -> None:
    """Periodic health check + heartbeat log to DB."""
    from src.gateway_log import log_health_ok, log_health_fail, log_uptime
    while not _shutdown:
        time.sleep(30)
        if _shutdown:
            break
        health = _health_check()
        if health.get("ok"):
            log_health_ok("web", health.get("latency_ms", 0))
        else:
            log_health_fail("web", health.get("error", "unknown"))
            if verbose:
                logger.warning("Health check failed: %s", health.get("error"))
        uptime = time.time() - _start_time
        log_uptime(_services, uptime)


# ── Main ────────────────────────────────────────────────────────────────

verbose = False


def main() -> None:
    global verbose, _start_time
    _start_time = time.time()

    parser = argparse.ArgumentParser(description="Kairos Gateway — unified launcher")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs in console")
    parser.add_argument("--no-web", action="store_true", help="Skip web dashboard")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram bot")
    parser.add_argument("--no-searxng", action="store_true", help="Skip SearXNG")
    args = parser.parse_args()
    verbose = args.verbose

    _cleanup_orphans()

    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print()
    for line in BANNER.rstrip("\n").split("\n"):
        print(f"  {CYAN}{line}{RESET}")
    print()

    from src.memory.schema import init_db
    root_logger = logging.getLogger()
    prev_level = root_logger.level
    root_logger.setLevel(logging.WARNING)
    asyncio.run(init_db())
    root_logger.setLevel(prev_level)

    from src.gateway_log import log_startup

    _log_starting("Memory DB")
    _log_ok("Memory DB", DEFAULT_CONFIG.memory_db_path)
    log_startup("memory_db", DEFAULT_CONFIG.memory_db_path)

    services: dict[str, dict[str, Any]] = {}
    services["Web Dashboard"] = {
        "running": False,
        "url": f"http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}",
    }
    services["SearXNG"] = {
        "running": False,
        "url": DEFAULT_CONFIG.searxng_url,
    }
    if DEFAULT_CONFIG.telegram_bot_token:
        services["Telegram Bot"] = {"running": False, "detail": "polling"}
    else:
        services["Telegram Bot"] = {"running": False, "detail": "no token"}
    services["Memory DB"] = {"running": True, "url": DEFAULT_CONFIG.memory_db_path, "detail": "sqlite"}

    if not args.no_searxng:
        _log_starting("SearXNG")
        services["SearXNG"]["running"] = _start_searxng(verbose)
        if services["SearXNG"]["running"]:
            _log_ok("SearXNG", DEFAULT_CONFIG.searxng_url)
            log_startup("searxng", DEFAULT_CONFIG.searxng_url)
        else:
            _log_skip("SearXNG", "not installed or disabled")

    if not args.no_web:
        _log_starting("Web Dashboard")
        web_proc = _start_web(verbose)
        services["Web Dashboard"]["running"] = web_proc is not None
        services["Web Dashboard"]["process"] = web_proc
        if web_proc:
            _log_ok("Web Dashboard", f"http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}")
            log_startup("web", f"http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}", web_proc.pid)
        else:
            _log_fail("Web Dashboard", "failed to start")
            log_startup("web", "failed to start")

    if not args.no_telegram and DEFAULT_CONFIG.telegram_bot_token:
        _log_starting("Telegram Bot")
        tg_proc = _start_telegram(verbose)
        services["Telegram Bot"]["running"] = tg_proc is not None
        services["Telegram Bot"]["process"] = tg_proc
        if tg_proc:
            _log_ok("Telegram Bot", "polling")
            log_startup("telegram", "polling", tg_proc.pid)
        else:
            _log_fail("Telegram Bot", "failed to start")
    elif not args.no_telegram:
        _log_skip("Telegram Bot", "no token")

    _services.clear()
    _services.update(services)

    _print_services(services, verbose)
    log_startup("gateway", f"pid={os.getpid()}", os.getpid())

    signal.signal(signal.SIGINT, lambda *_: (_stop_all(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (_stop_all(), sys.exit(0)))
    signal.signal(signal.SIGUSR1, _handle_sigusr1)
    signal.signal(signal.SIGHUP, _handle_sighup)
    signal.signal(signal.SIGCHLD, _handle_sigchld)

    import threading
    hb_thread = threading.Thread(target=_heartbeat_loop, args=(verbose,), daemon=True)
    hb_thread.start()

    try:
        time.sleep(3)
        while not _shutdown:
            dead = _check_alive()
            if dead:
                from src.gateway_log import log_crash
                log_crash("gateway", dead)
                print(f"\n  {RED}✗{RESET} {dead} stopped unexpectedly")
                _stop_all()
                sys.exit(1)
            time.sleep(2)
    except KeyboardInterrupt:
        _stop_all()


if __name__ == "__main__":
    main()
