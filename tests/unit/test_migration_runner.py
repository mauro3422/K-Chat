import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

from src.memory.migration_runner import run_pending_migrations


@pytest.mark.anyio
async def test_run_pending_migrations_applies_new_migrations_and_commits():
    conn = AsyncMock()
    engine = AsyncMock()
    migrations = [MagicMock(), MagicMock(), MagicMock()]
    migrations[1] = AsyncMock()
    migrations[2] = AsyncMock()

    await run_pending_migrations(conn, engine, migrations, current_version=1)

    migrations[1].assert_called_once_with(conn, engine)
    migrations[2].assert_called_once_with(conn, engine)
    assert engine.commit.call_count == 2


@pytest.mark.anyio
async def test_run_pending_migrations_skips_when_schema_is_current():
    conn = AsyncMock()
    engine = AsyncMock()
    migrations = [MagicMock(), MagicMock()]

    await run_pending_migrations(conn, engine, migrations, current_version=2)

    conn.cursor.return_value.execute.assert_not_called()
    engine.commit.assert_not_called()
