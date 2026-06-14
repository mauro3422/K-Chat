import pytest
from unittest.mock import AsyncMock, MagicMock

import src.memory.connection_pool as connection
import src.memory.bootstrap as bootstrap


@pytest.mark.anyio
async def test_get_conn_initializes_each_db_path_once(monkeypatch):
    raw_one = AsyncMock()
    init_calls: list[str] = []

    async def fake_get_raw_conn(db_path):
        return raw_one

    async def fake_ensure(path):
        init_calls.append(path)

    monkeypatch.setattr(connection, "get_raw_conn", fake_get_raw_conn)
    monkeypatch.setattr(bootstrap, "ensure_db_initialized", fake_ensure)
    monkeypatch.setattr(connection, "_conn_storage", {"conn": None, "db_path": None})
    monkeypatch.setattr(connection, "resolve_db_path", lambda: "/tmp/kairos-test.db")

    conn_one = await connection.get_conn()
    assert conn_one._conn is raw_one
    assert init_calls == ["/tmp/kairos-test.db"]
    assert connection._conn_storage["conn"] is raw_one
    assert connection._conn_storage["db_path"] == "/tmp/kairos-test.db"

    conn_two = await connection.get_conn()
    assert conn_two._conn is raw_one
    assert init_calls == ["/tmp/kairos-test.db"]


@pytest.mark.anyio
async def test_get_conn_replaces_stale_connection_when_db_path_changes(monkeypatch):
    raw_one = AsyncMock()
    raw_two = AsyncMock()

    async def fake_get_raw_conn(db_path):
        return raw_one if db_path == "/tmp/kairos-old.db" else raw_two

    async def fake_ensure(path):
        pass

    monkeypatch.setattr(connection, "get_raw_conn", fake_get_raw_conn)
    monkeypatch.setattr(bootstrap, "ensure_db_initialized", fake_ensure)
    monkeypatch.setattr(connection, "_conn_storage", {"conn": raw_one, "db_path": "/tmp/kairos-old.db"})

    monkeypatch.setattr(connection, "resolve_db_path", lambda: "/tmp/kairos-new.db")

    conn_two = await connection.get_conn()
    assert conn_two._conn is raw_two
    raw_one.close.assert_called_once()
