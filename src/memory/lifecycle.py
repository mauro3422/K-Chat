import threading
from typing import Callable

_init_lock = threading.Lock()
_initialized_db_paths: set[str] = set()


def mark_initialized(db_path: str) -> None:
    with _init_lock:
        _initialized_db_paths.add(db_path)


def is_initialized(db_path: str) -> bool:
    with _init_lock:
        return db_path in _initialized_db_paths


async def ensure_initialized(db_path: str, initializer: Callable[[str], Any]) -> None:
    if is_initialized(db_path):
        return
    await initializer(db_path)


def clear_initialized() -> None:
    with _init_lock:
        _initialized_db_paths.clear()
