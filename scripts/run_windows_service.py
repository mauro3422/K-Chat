"""Hidden Windows entry point with durable stdout/stderr logging."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = (log_dir / "windows-service.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    os.chdir(root)

    import uvicorn

    uvicorn.run(
        "web.server:app",
        host="0.0.0.0",
        port=args.port,
        access_log=False,
        timeout_graceful_shutdown=8,
    )


if __name__ == "__main__":
    main()
