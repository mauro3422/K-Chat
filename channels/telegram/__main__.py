"""Entry point: ``python -m channels.telegram``.

Starts the Telegram bot in polling mode.
Single-instance via PID lock file at ``.kairos/telegram_bot.pid``.
"""

from __future__ import annotations

import argparse
import atexit
import logging
import os
import sys
from pathlib import Path

from channels.telegram.config import load_telegram_config
from channels.telegram.bot import run_bot

_PID_FILE = Path(__file__).resolve().parent.parent.parent / ".kairos" / "telegram_bot.pid"


def _check_pid_lock() -> None:
    """Exit if another bot instance is running. Write PID file on success."""
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if _PID_FILE.exists():
        try:
            old_pid = int(_PID_FILE.read_text().strip())
            # Check if that PID is still alive and is a python process
            try:
                os.kill(old_pid, 0)
                # Process exists — check if it's actually us
                with open(f"/proc/{old_pid}/cmdline", "rb") as fh:
                    cmdline = fh.read().decode("utf-8", errors="replace")
                if "channels.telegram" in cmdline:
                    print(f"❌ Bot ya está corriendo (PID {old_pid}).")
                    print("   Si querés forzar reinicio, borrá:")
                    print(f"   rm {_PID_FILE}")
                    sys.exit(1)
            except (OSError, IOError, ValueError):
                pass  # PID not alive or not accessible
        except (OSError, ValueError):
            pass  # Invalid PID file

    # Write our PID
    _PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: _PID_FILE.unlink(missing_ok=True))


def main() -> None:
    _check_pid_lock()

    parser = argparse.ArgumentParser(description="K-Chat Telegram Bot")
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--token",
        type=str,
        default="",
        help="Telegram bot token (overrides TELEGRAM_BOT_TOKEN env)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force start even if PID file exists (ignores lock)",
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.token:
        os.environ["TELEGRAM_BOT_TOKEN"] = args.token

    config = load_telegram_config()

    if not config.enabled:
        print("❌ TELEGRAM_BOT_TOKEN not set.")
        print("   Set the environment variable or pass --token")
        sys.exit(1)

    try:
        import asyncio
        asyncio.run(run_bot(config))
    except KeyboardInterrupt:
        print("\n👋 Bye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
