from unittest.mock import MagicMock

import src.memory.connection_pool as connection
import src.memory.lifecycle as lifecycle
import src.memory.schema as schema


def test_get_conn_initializes_each_db_path_once(monkeypatch):
    raw_one = MagicMock()
    raw_two = MagicMock()
    init_calls: list[str] = []

    def fake_init(path: str) -> None:
        init_calls.append(path)
        lifecycle.mark_initialized(path)

    monkeypatch.setattr(connection, "resolve_db_path", lambda config=None: "/tmp/kairos-test.db")
    monkeypatch.setattr(connection, "get_raw_conn", MagicMock(side_effect=[raw_one, raw_two]))
    monkeypatch.setattr(schema, "init_db_for_path", fake_init)
    lifecycle.clear_initialized()
    for attr in ("conn", "db_path"):
        if hasattr(connection._thread_local, attr):
            delattr(connection._thread_local, attr)

    conn_one = connection.get_conn()
    assert conn_one._conn is raw_one
    assert init_calls == ["/tmp/kairos-test.db"]

    for attr in ("conn", "db_path"):
        if hasattr(connection._thread_local, attr):
            delattr(connection._thread_local, attr)

    conn_two = connection.get_conn()
    assert conn_two._conn is raw_two
    assert init_calls == ["/tmp/kairos-test.db"]


def test_get_conn_replaces_stale_connection_when_db_path_changes(monkeypatch):
    raw_one = MagicMock()
    raw_two = MagicMock()
    init_calls: list[str] = []
    paths = iter(["/tmp/kairos-old.db", "/tmp/kairos-new.db"])

    def fake_init(path: str) -> None:
        init_calls.append(path)
        lifecycle.mark_initialized(path)

    monkeypatch.setattr(connection, "resolve_db_path", lambda config=None: next(paths))
    monkeypatch.setattr(connection, "get_raw_conn", MagicMock(side_effect=[raw_one, raw_two]))
    monkeypatch.setattr(schema, "init_db_for_path", fake_init)
    lifecycle.clear_initialized()
    for attr in ("conn", "db_path"):
        if hasattr(connection._thread_local, attr):
            delattr(connection._thread_local, attr)

    conn_one = connection.get_conn()
    assert conn_one._conn is raw_one

    conn_two = connection.get_conn()
    assert conn_two._conn is raw_two
    raw_one.close.assert_called_once()
    assert init_calls == ["/tmp/kairos-old.db", "/tmp/kairos-new.db"]
