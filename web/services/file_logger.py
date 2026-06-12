import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

LOG_DIR = Path(os.environ.get("KAIROS_LOG_DIR", "logs"))
SERVER_LOG_DIR = LOG_DIR / "server"
CLIENT_LOG_DIR = LOG_DIR / "client"


class JsonlHandler(logging.Handler):
    """Logging handler that writes structured JSONL to logs/server/YYYY-MM-DD.jsonl

    Each line is a JSON object with keys:
      t  — ISO-8601 timestamp (UTC)
      l  — level (D, I, W, E)
      m  — module name
      msg — log message
      d  — optional data dict (from record.data or extra)
    """

    def __init__(self, module: str = "app", level: int = logging.DEBUG):
        super().__init__(level)
        self.module = module
        _ensure_dirs()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = self._build_entry(record)
            path = SERVER_LOG_DIR / f"{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
            with open(path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            self.handleError(record)

    def _build_entry(self, record: logging.LogRecord) -> dict:
        data = getattr(record, "data", None)
        if data is None and record.args:
            try:
                data = {"args": record.args}
            except Exception:
                data = None
        return {
            "t": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "l": record.levelname[0],
            "m": record.name,
            "msg": record.getMessage(),
            "d": data,
        }


def _ensure_dirs() -> None:
    SERVER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    CLIENT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def install_jsonl_handler(module: str = "app") -> JsonlHandler:
    handler = JsonlHandler(module)
    logger = logging.getLogger(module)
    logger.addHandler(handler)
    return handler


# Install on root logger at import time so ALL named loggers are captured
logging.root.addHandler(JsonlHandler("root"))
