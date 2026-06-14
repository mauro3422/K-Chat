import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.config_loader import load_config


class JsonlHandler(logging.Handler):
    """Logging handler that writes structured JSONL to logs/server/YYYY-MM-DD.jsonl

    Each line is a JSON object with keys:
      t  — ISO-8601 timestamp (UTC)
      l  — level (D, I, W, E)
      m  — module name
      msg — log message
      d  — optional data dict (from record.data or extra)
    """

    def __init__(self, module: str = "app", level: int = logging.DEBUG, config=None):
        super().__init__(level)
        self.module = module
        if config is None:
            config = load_config()
        self._server_log_dir = Path(config.kairos_log_dir) / "server"
        self._client_log_dir = Path(config.kairos_log_dir) / "client"
        self._ensure_dirs()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = self._build_entry(record)
            path = self._server_log_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
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
            "t": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "l": record.levelname[0],
            "m": record.name,
            "msg": record.getMessage(),
            "d": data,
        }


def _ensure_dirs() -> None:
    pass


def install_jsonl_handler(module: str = "app", config=None) -> JsonlHandler:
    handler = JsonlHandler(module, config=config)
    logger = logging.getLogger(module)
    logger.addHandler(handler)
    return handler
