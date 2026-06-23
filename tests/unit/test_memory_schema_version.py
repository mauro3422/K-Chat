import sqlite3

import pytest


@pytest.mark.anyio
async def test_session_schema_treats_empty_version_table_as_zero(tmp_path):
    database = tmp_path / "sessions.db"

    from src.memory.schema import init_db_for_path

    await init_db_for_path(str(database))

    connection = sqlite3.connect(database)
    version = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()

    assert version is not None
    assert "sessions" in tables


@pytest.mark.anyio
async def test_memory_schema_uses_independent_version_table(tmp_path, monkeypatch):
    database = tmp_path / "shared.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_version (version INTEGER)")
    connection.execute("INSERT INTO schema_version VALUES (23)")
    connection.execute(
        "CREATE TABLE memory_index (session_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT, updated_at TEXT)"
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", str(database))
    from src.memory.memory_schema import init_memory_db

    await init_memory_db()

    connection = sqlite3.connect(database)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(memory_index)")}
    version = connection.execute("SELECT MAX(version) FROM memory_schema_version").fetchone()[0]
    session_version = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    connection.close()

    assert "session_id" not in columns
    assert {"key", "value", "weight"}.issubset(columns)
    assert version == 12
    assert session_version == 23
