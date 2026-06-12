"""Backward-compatible database facade.

New code should prefer `src.memory.connection` and `src.memory.schema`.
"""

from src.memory.connection import (
    DatabaseEngine,
    PooledConnection,
    get_conn,
    get_engine,
    set_engine,
)
from src.memory.schema import init_db

__all__ = [
    "DatabaseEngine",
    "PooledConnection",
    "get_conn",
    "get_engine",
    "set_engine",
    "init_db",
]
