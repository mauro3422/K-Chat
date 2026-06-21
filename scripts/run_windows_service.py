"""Hidden Windows entry point with durable stdout/stderr logging."""

from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path


class RotatingTextStream:
    """Small file-like stream with bounded size and numbered backups."""

    def __init__(self, path: Path, *, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 4) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._lock = threading.Lock()
        self._size = path.stat().st_size if path.exists() else 0
        self._stream = path.open("a", encoding="utf-8", buffering=1)

    def write(self, message: str) -> int:
        encoded_size = len(message.encode("utf-8"))
        with self._lock:
            if self._size and self._size + encoded_size > self._max_bytes:
                self._rotate()
            written = self._stream.write(message)
            self._size += encoded_size
            return written

    def flush(self) -> None:
        with self._lock:
            self._stream.flush()

    def isatty(self) -> bool:
        return False

    def _rotate(self) -> None:
        self._stream.close()
        oldest = self._path.with_suffix(self._path.suffix + f".{self._backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(self._backup_count - 1, 0, -1):
            source = self._path.with_suffix(self._path.suffix + f".{index}")
            if source.exists():
                source.replace(self._path.with_suffix(self._path.suffix + f".{index + 1}"))
        if self._path.exists():
            self._path.replace(self._path.with_suffix(self._path.suffix + ".1"))
        self._stream = self._path.open("a", encoding="utf-8", buffering=1)
        self._size = 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = RotatingTextStream(log_dir / "windows-service.log")
    sys.stdout = stream
    sys.stderr = stream
    os.chdir(root)
    sys.path.insert(0, str(root))

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
