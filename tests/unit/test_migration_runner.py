from unittest.mock import MagicMock

from src.memory.migration_runner import run_pending_migrations


def test_run_pending_migrations_applies_new_migrations_and_commits():
    conn = MagicMock()
    engine = MagicMock()
    migrations = [MagicMock(), MagicMock(), MagicMock()]

    run_pending_migrations(conn, engine, migrations, current_version=1)

    migrations[1].assert_called_once_with(conn, engine)
    migrations[2].assert_called_once_with(conn, engine)
    assert conn.cursor.return_value.execute.call_count == 4
    assert engine.commit.call_count == 2


def test_run_pending_migrations_skips_when_schema_is_current():
    conn = MagicMock()
    engine = MagicMock()
    migrations = [MagicMock(), MagicMock()]

    run_pending_migrations(conn, engine, migrations, current_version=2)

    conn.cursor.return_value.execute.assert_not_called()
    engine.commit.assert_not_called()
