import pytest
from unittest.mock import AsyncMock

from src.memory.connection_pool import get_conn, return_conn


@pytest.mark.anyio
async def test_get_conn_creates_new_connection_on_first_call(monkeypatch):
    raw = AsyncMock()
    monkeypatch.setattr("src.memory.connection_pool.create_raw_conn", AsyncMock(return_value=raw))
    monkeypatch.setattr("src.memory.connection_pool.resolve_db_path", lambda: "/tmp/kairos-test.db")

    pooled = await get_conn()
    assert pooled._conn is raw
    assert pooled._db_path == "/tmp/kairos-test.db"


@pytest.mark.anyio
async def test_get_conn_reuses_pooled_connection(monkeypatch):
    raw = AsyncMock()
    create_calls = []
    async def fake_create(db_path):
        create_calls.append(db_path)
        return raw
    monkeypatch.setattr("src.memory.connection_pool.create_raw_conn", fake_create)
    monkeypatch.setattr("src.memory.connection_pool.resolve_db_path", lambda: "/tmp/kairos-test.db")

    c1 = await get_conn()
    assert len(create_calls) == 1

    await return_conn("/tmp/kairos-test.db", c1)

    c2 = await get_conn()
    assert c2._conn is raw
    assert len(create_calls) == 1


@pytest.mark.anyio
async def test_get_conn_creates_new_when_pool_empty(monkeypatch):
    raw_one = AsyncMock()
    raw_two = AsyncMock()
    calls = []
    async def fake_create(db_path):
        conn = raw_two if calls else raw_one
        calls.append(conn)
        return conn
    monkeypatch.setattr("src.memory.connection_pool.create_raw_conn", fake_create)
    monkeypatch.setattr("src.memory.connection_pool.resolve_db_path", lambda: "/tmp/kairos-test.db")

    c1 = await get_conn()
    assert c1._conn is raw_one

    c2 = await get_conn()
    assert c2._conn is raw_two
