"""Entry point: ``python -m channels.telegram``.

Starts the Telegram bot in polling mode.
"""

from __future__ import annotations

import argparse
import logging
import sys

from channels.telegram.config import load_telegram_config
from channels.telegram.bot import run_bot


def main() -> None:
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
    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Override token if provided via CLI
    if args.token:
        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = args.token

    config = load_telegram_config()

    if not config.enabled:
        print("❌ TELEGRAM_BOT_TOKEN not set.")
        print("   Set the environment variable or pass --token")
        sys.exit(1)

    try:
        run_bot(config)
    except KeyboardInterrupt:
        print("\n👋 Bye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
