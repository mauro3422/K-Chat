import logging
from typing import Any

_backend_log_buffer = []
_max_backend_logs = 100


class BackendLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global _backend_log_buffer
        try:
            log_entry = {
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()
            }
            _backend_log_buffer.append(log_entry)
            if len(_backend_log_buffer) > _max_backend_logs:
                _backend_log_buffer = _backend_log_buffer[-_max_backend_logs:]
        except Exception:
            pass


def get_backend_logs() -> list[dict[str, Any]]:
    return list(_backend_log_buffer)


# Install handler at import time
_backend_handler = BackendLogHandler()
logging.getLogger("kairos").addHandler(_backend_handler)
logging.getLogger("kairos.src.llm").setLevel(logging.INFO)
logging.getLogger("kairos.web.routers.chat").setLevel(logging.INFO)
