from contextvars import ContextVar
from typing import Any, Protocol


class DatabaseEngine(Protocol):
    def connect(self) -> Any: ...
    def execute(self, conn: Any, sql: str, params: tuple = ()) -> Any: ...
    def commit(self, conn: Any) -> None: ...
    def rollback(self, conn: Any) -> None: ...
    def close(self, conn: Any) -> None: ...
_current_engine: ContextVar[DatabaseEngine | None] = ContextVar(
    "kairos_memory_engine",
    default=None,
)


def configure_engine(engine: DatabaseEngine | None) -> None:
    """Set the active database engine explicitly, or clear it with None."""
    _current_engine.set(engine)


def reset_engine() -> None:
    """Clear the active database engine for the current context."""
    _current_engine.set(None)


def get_engine() -> DatabaseEngine | None:
    return _current_engine.get()


def set_engine(engine: DatabaseEngine | None) -> None:
    configure_engine(engine)


def clear_engine() -> None:
    reset_engine()
