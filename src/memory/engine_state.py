from typing import Any, Protocol


class DatabaseEngine(Protocol):
    def connect(self) -> Any: ...
    def execute(self, conn: Any, sql: str, params: tuple = ()) -> Any: ...
    def commit(self, conn: Any) -> None: ...
    def rollback(self, conn: Any) -> None: ...
    def close(self, conn: Any) -> None: ...


class EngineState:
    """Holds the current database engine (for test injection)."""

    def __init__(self) -> None:
        self._engine: DatabaseEngine | None = None

    def get(self) -> DatabaseEngine | None:
        return self._engine

    def set(self, engine: DatabaseEngine | None) -> None:
        self._engine = engine

    def clear(self) -> None:
        self._engine = None


_engine_state = EngineState()


def get_engine() -> DatabaseEngine | None:
    return _engine_state.get()


def set_engine(engine: DatabaseEngine | None) -> None:
    _engine_state.set(engine)


def clear_engine() -> None:
    _engine_state.clear()
