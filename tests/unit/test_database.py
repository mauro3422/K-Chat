from unittest.mock import MagicMock

import src.memory.connection as connection
import src.memory.schema as schema
import src.memory.database as database


def test_get_conn_initializes_each_db_path_once(monkeypatch):
    raw_one = MagicMock()
    raw_two = MagicMock()
    init_calls: list[str] = []

    def fake_init(path: str) -> None:
        init_calls.append(path)
        schema._mark_initialized(path)

    monkeypatch.setattr(connection, "_get_db_path", lambda: "/tmp/kairos-test.db")
    monkeypatch.setattr(connection, "_get_raw_conn", MagicMock(side_effect=[raw_one, raw_two]))
    monkeypatch.setattr(schema, "init_db_for_path", fake_init)
    schema._initialized_db_paths.clear()
    for attr in ("conn", "db_path"):
        if hasattr(connection._thread_local, attr):
            delattr(connection._thread_local, attr)

    conn_one = database.get_conn()
    assert conn_one._conn is raw_one
    assert init_calls == ["/tmp/kairos-test.db"]

    for attr in ("conn", "db_path"):
        if hasattr(connection._thread_local, attr):
            delattr(connection._thread_local, attr)

    conn_two = database.get_conn()
    assert conn_two._conn is raw_two
    assert init_calls == ["/tmp/kairos-test.db"]
