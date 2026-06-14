import pytest
from unittest.mock import AsyncMock
import sqlite3
from unittest.mock import MagicMock

from src.memory.migrations import (
    _migration_001_initial_schema,
    _migration_002_add_reasoning,
    _migration_003_add_tool_call_turn,
    _migration_004_add_phases,
    _migration_005_add_tool_calls,
    _migration_006_add_tool_call_id,
    _migration_007_saved_widgets_global,
    _migration_008_add_token_counts,
    _migration_009_add_indexes,
    _migration_010_memory_index,
    _migration_011_cleanup_orphans,
    MIGRATIONS,
)


class TestMigration001InitialSchema:
    @pytest.mark.anyio
    async def test_creates_all_tables(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_001_initial_schema(conn, engine)
        assert engine.execute.call_count == 5


class TestMigration002AddReasoning:
    @pytest.mark.anyio
    async def test_adds_column(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_002_add_reasoning(conn, engine)
        engine.execute.assert_called_once_with(
            conn, "ALTER TABLE messages ADD COLUMN reasoning TEXT DEFAULT ''"
        )

    @pytest.mark.anyio
    async def test_handles_duplicate_column(self):
        conn = MagicMock()
        engine = AsyncMock()
        engine.execute.side_effect = sqlite3.OperationalError("duplicate column")
        await _migration_002_add_reasoning(conn, engine)
        engine.execute.assert_called_once()


class TestMigration003AddToolCallTurn:
    @pytest.mark.anyio
    async def test_adds_turn_column(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_003_add_tool_call_turn(conn, engine)
        engine.execute.assert_called_once_with(
            conn, "ALTER TABLE tool_calls ADD COLUMN turn INTEGER DEFAULT 0"
        )

    @pytest.mark.anyio
    async def test_handles_duplicate_column(self):
        conn = MagicMock()
        engine = AsyncMock()
        engine.execute.side_effect = sqlite3.OperationalError("duplicate column")
        await _migration_003_add_tool_call_turn(conn, engine)
        engine.execute.assert_called_once()


class TestMigration004AddPhases:
    @pytest.mark.anyio
    async def test_adds_phases_column(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_004_add_phases(conn, engine)
        engine.execute.assert_called_once_with(
            conn, "ALTER TABLE messages ADD COLUMN phases TEXT DEFAULT '[]'"
        )


class TestMigration005AddToolCalls:
    @pytest.mark.anyio
    async def test_adds_tool_calls_column(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_005_add_tool_calls(conn, engine)
        engine.execute.assert_called_once_with(
            conn, "ALTER TABLE messages ADD COLUMN tool_calls TEXT"
        )


class TestMigration006AddToolCallId:
    @pytest.mark.anyio
    async def test_adds_tool_call_id_column(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_006_add_tool_call_id(conn, engine)
        engine.execute.assert_called_once_with(
            conn, "ALTER TABLE messages ADD COLUMN tool_call_id TEXT"
        )


class TestMigration007SavedWidgetsGlobal:
    @pytest.mark.anyio
    async def test_creates_fresh_schema_when_no_table(self):
        conn = MagicMock()
        engine = AsyncMock()
        engine.execute.return_value = AsyncMock()
        engine.execute.return_value.fetchone = AsyncMock(return_value=None)
        await _migration_007_saved_widgets_global(conn, engine)
        assert engine.execute.call_count >= 3

    @pytest.mark.anyio
    async def test_migrates_old_schema_when_session_id_has_default(self):
        conn = MagicMock()
        engine = AsyncMock()
        fetchone = AsyncMock(return_value=("saved_widgets",))
        fetchall = AsyncMock(return_value=[
            {"cid": 0, "name": "widget_id", "type": "TEXT", "notnull": 0, "dflt_value": None, "pk": 0},
            {"cid": 1, "name": "session_id", "type": "TEXT", "notnull": 0, "dflt_value": None, "pk": 1},
        ])
        result_mock = AsyncMock()
        result_mock.fetchone = fetchone
        result_mock.fetchall = fetchall
        engine.execute.return_value = result_mock
        await _migration_007_saved_widgets_global(conn, engine)
        assert engine.execute.call_count >= 10

    @pytest.mark.anyio
    async def test_creates_fresh_schema_when_session_id_has_no_default(self):
        conn = MagicMock()
        engine = AsyncMock()
        fetchone = AsyncMock(side_effect=[
            ("saved_widgets",),
            (("widget_id", "TEXT", 0, None, 0), ("session_id", "TEXT", 0, None, 0)),
        ])
        result_mock = AsyncMock()
        result_mock.fetchone = fetchone
        engine.execute.return_value = result_mock
        await _migration_007_saved_widgets_global(conn, engine)
        assert engine.execute.call_count >= 3


class TestMigration008AddTokenCounts:
    @pytest.mark.anyio
    async def test_adds_three_columns(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_008_add_token_counts(conn, engine)
        assert engine.execute.call_count == 3

    @pytest.mark.anyio
    async def test_handles_duplicates(self):
        conn = MagicMock()
        engine = AsyncMock()
        engine.execute.side_effect = sqlite3.OperationalError("duplicate")
        await _migration_008_add_token_counts(conn, engine)
        assert engine.execute.call_count == 3


class TestMigration009AddIndexes:
    @pytest.mark.anyio
    async def test_creates_indexes(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_009_add_indexes(conn, engine)
        assert engine.execute.call_count == 4


class TestMigration010MemoryIndex:
    @pytest.mark.anyio
    async def test_creates_table_and_index(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_010_memory_index(conn, engine)
        assert engine.execute.call_count == 2


class TestMigration011CleanupOrphans:
    @pytest.mark.anyio
    async def test_deletes_orphans_and_creates_triggers(self):
        conn = MagicMock()
        engine = AsyncMock()
        await _migration_011_cleanup_orphans(conn, engine)
        assert engine.execute.call_count == 10


class TestMigrationRegistry:
    @pytest.mark.anyio
    async def test_all_migrations_are_callable(self):
        for m in MIGRATIONS:
            assert callable(m)

    @pytest.mark.anyio
    async def test_migration_count(self):
        assert len(MIGRATIONS) == 15
