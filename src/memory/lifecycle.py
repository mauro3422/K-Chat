"""Database initialization lifecycle management.

Uses module-level Lock and set as intentional initialization guards
to prevent double-initialization of database paths across the app.
"""

import threading
from typing import Any, Callable

_init_lock = threading.Lock()              # Intentional init guard — prevents
_initialized_db_paths: set[str] = set()    # double-init of database paths


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
