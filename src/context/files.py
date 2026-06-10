import os
import logging

logger = logging.getLogger(__name__)


def _ensure_file(path: str, template: str) -> None:
    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(template)
    except OSError as e:
        logger.warning("Could not create %s: %s", path, e)


def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError as e:
        logger.warning("Could not read %s: %s", path, e)
        return ""
