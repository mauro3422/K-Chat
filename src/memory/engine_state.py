from typing import Any, Protocol


class DatabaseEngine(Protocol):
    def connect(self) -> Any: ...
    def execute(self, conn: Any, sql: str, params: tuple = ()) -> Any: ...
    def commit(self, conn: Any) -> None: ...
    def rollback(self, conn: Any) -> None: ...
    def close(self, conn: Any) -> None: ...


_engine: DatabaseEngine | None = None


def get_engine() -> DatabaseEngine | None:
    return _engine


def set_engine(engine: DatabaseEngine | None) -> None:
    global _engine
    _engine = engine
