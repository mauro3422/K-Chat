import pytest
from unittest.mock import patch, AsyncMock

from src.memory.repos import (
    MessageRecord,
    MessageRepository,
    SessionRepository,
    ToolCallRepository,
    WidgetStateRepository,
    DebugRepository,
    SavedWidgetRepository,
    MemoryIndexRepository,
    get_repos,
)


class TestMessageRecord:
    @pytest.mark.anyio
    async def test_default_values(self):
        record = MessageRecord()
        assert record.session_id == ""
        assert record.role == ""
        assert record.content == ""
        assert record.model is None
        assert record.reasoning == ""
        assert record.phases == "[]"
        assert record.prompt_tokens == 0
        assert record.completion_tokens == 0
        assert record.total_tokens == 0
        assert record.tool_calls is None
        assert record.tool_call_id is None

    @pytest.mark.anyio
    async def test_custom_values(self):
        record = MessageRecord(
            session_id="sess_1",
            role="user",
            content="hello",
            model="model-x",
            reasoning="thinking...",
            phases='["phase1"]',
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            tool_calls='[{"name":"test"}]',
            tool_call_id="call_123",
        )
        assert record.session_id == "sess_1"
        assert record.role == "user"
        assert record.content == "hello"
        assert record.model == "model-x"
        assert record.reasoning == "thinking..."
        assert record.phases == '["phase1"]'
        assert record.prompt_tokens == 10
        assert record.completion_tokens == 20
        assert record.total_tokens == 30
        assert record.tool_calls == '[{"name":"test"}]'
        assert record.tool_call_id == "call_123"


class TestMessageRepository:
    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_save(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = MessageRepository()

        await repo.save("sess_1", "user", "hello", "model-x")

        args = conn.execute.call_args
        assert "INSERT INTO messages" in args[0][0]
        assert args[0][1][0] == "sess_1"
        assert args[0][1][1] == "user"
        assert args[0][1][2] == "hello"
        assert args[0][1][3] == "model-x"
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_save_with_none_content(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = MessageRepository()

        await repo.save("sess_1", "assistant", None, "model-x")

        args = conn.execute.call_args
        assert args[0][1][2] == ""

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_save_record(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = MessageRepository()

        record = MessageRecord(
            session_id="sess_1",
            role="user",
            content="via record",
            model="m1",
        )
        await repo.save_record(record)

        conn.execute.assert_called_once()
        args = conn.execute.call_args
        assert args[0][1][0] == "sess_1"
        assert args[0][1][1] == "user"
        assert args[0][1][2] == "via record"
        assert args[0][1][3] == "m1"

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_session_messages(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [
            ("user", "hi", "m1", "2024-01-01", "", "[]", None, None)
        ]
        mock_get_conn.return_value = conn
        repo = MessageRepository()

        result = await repo.get_session_messages("sess_1", limit=10)

        conn.execute.assert_called_once()
        args = conn.execute.call_args
        assert args[0][1] == ("sess_1", 10)
        assert result == [("user", "hi", "m1", "2024-01-01", "", "[]", None, None)]


class TestSessionRepository:
    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_ensure_creates_when_missing(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = None
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        await repo.ensure("sess_new")

        assert conn.execute.call_count == 2
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_ensure_skips_when_exists(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = (1,)
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        await repo.ensure("sess_existing")

        assert conn.execute.call_count == 1
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_rename(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        await repo.rename("sess_1", "New Name")

        args = conn.execute.call_args
        assert args[0][1] == ("New Name", "sess_1")
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_delete(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        await repo.delete("sess_1")

        assert conn.execute.call_count == 1
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_all(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [("sess_1", "t1", "t2", 5, 2, "My Session")]
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        result = await repo.get_all(limit=10)

        args = conn.execute.call_args
        assert args[0][1] == (10,)
        assert result == [("sess_1", "t1", "t2", 5, 2, "My Session")]

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_check_should_rename_empty_name_one_message(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.side_effect = [{"name": ""}, (1,)]
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        assert await repo.check_should_rename("sess_1") is True

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_check_should_rename_none_name(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.side_effect = [{"name": None}, (1,)]
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        assert await repo.check_should_rename("sess_1") is True

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_check_should_rename_already_named(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = {"name": "My Session"}
        mock_get_conn.return_value = conn
        repo = SessionRepository()

        assert await repo.check_should_rename("sess_1") is False
        conn.execute.assert_called_once()


class TestToolCallRepository:
    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_log(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = ToolCallRepository()

        await repo.log("sess_1", "get_weather", '{"city":"NYC"}', "success", turn=1)

        args = conn.execute.call_args
        assert "INSERT INTO tool_calls" in args[0][0]
        assert args[0][1][:4] == ("sess_1", "get_weather", '{"city":"NYC"}', "success")
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_history(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [
            ("get_weather", '{"city":"NYC"}', "success", "2024-01-01", 1)
        ]
        mock_get_conn.return_value = conn
        repo = ToolCallRepository()

        result = await repo.get_history("sess_1", limit=5)

        args = conn.execute.call_args
        assert args[0][1] == ("sess_1", 5)
        assert result == [("get_weather", '{"city":"NYC"}', "success", "2024-01-01", 1)]

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_record_execution(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = ToolCallRepository()

        await repo.record_execution(
            "sess_1",
            "get_weather",
            '{"city":"NYC"}',
            "success",
            "sunny",
            turn=2,
            tool_call_id="call_1",
        )

        assert conn.execute.call_count == 2
        first_args = conn.execute.call_args_list[0][0]
        second_args = conn.execute.call_args_list[1][0]
        assert "INSERT INTO tool_calls" in first_args[0]
        assert first_args[1][:4] == ("sess_1", "get_weather", '{"city":"NYC"}', "success")
        assert "INSERT INTO messages" in second_args[0]
        assert second_args[1][0] == "sess_1"
        assert second_args[1][1] == "tool"
        assert second_args[1][2] == "sunny"
        assert second_args[1][4] == "call_1"
        conn.commit.assert_called_once()


class TestWidgetStateRepository:
    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_save_state(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = WidgetStateRepository()

        await repo.save_state("sess_1", "widget_1", '{"x": 1}')

        conn.execute.assert_called_once()
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_states(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [{"widget_id": "w1", "state": '{"x":1}'}, {"widget_id": "w2", "state": '{"y":2}'}]
        mock_get_conn.return_value = conn
        repo = WidgetStateRepository()

        result = await repo.get_states("sess_1")

        assert result == {"w1": '{"x":1}', "w2": '{"y":2}'}


class TestDebugRepository:
    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_save_info(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        mock_get_conn.return_value = conn
        repo = DebugRepository()

        await repo.save_info("sess_1", {"model": "m1", "reasoning": "thinking"})

        args = conn.execute.call_args
        assert "INSERT OR REPLACE INTO debug_info" in args[0][0]
        assert args[0][1][0] == "sess_1"
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_info_found(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = {"model": "m1", "reasoning": "thinking", "system_prompt": "sys prompt", "tool_calls": "[]", "history_before": "[]", "asr_telemetry": "[]"}
        mock_get_conn.return_value = conn
        repo = DebugRepository()

        result = await repo.get_info("sess_1")

        assert result == {
            "model": "m1",
            "reasoning": "thinking",
            "system_prompt": "sys prompt",
            "tool_calls": [],
            "history_before": [],
            "asr_telemetry": [],
        }

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_info_missing(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = None
        mock_get_conn.return_value = conn
        repo = DebugRepository()

        result = await repo.get_info("sess_1")

        assert result == {}

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_info_parses_json(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = {"model": "m1", "reasoning": "", "system_prompt": "", "tool_calls": '[{"name":"test"}]', "history_before": '[{"role":"user"}]', "asr_telemetry": '[{"transport":"ws"}]'}
        mock_get_conn.return_value = conn
        repo = DebugRepository()

        result = await repo.get_info("sess_1")

        assert result["tool_calls"] == [{"name": "test"}]
        assert result["history_before"] == [{"role": "user"}]
        assert result["asr_telemetry"] == [{"transport": "ws"}]


class TestSavedWidgetRepository:
    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_save_new_widget(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = {"MAX(version)": 1}
        mock_get_conn.return_value = conn
        repo = SavedWidgetRepository()

        result = await repo.save("sess_1", "widget_1", "code here", "desc")

        assert conn.execute.call_count == 3
        assert result == {"widget_id": "widget_1", "version": 1, "status": "saved"}
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_save_existing_widget_increments_version(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = {"MAX(version)": 4}
        mock_get_conn.return_value = conn
        repo = SavedWidgetRepository()

        result = await repo.save("sess_1", "widget_1", "new code", "new desc")

        assert result == {"widget_id": "widget_1", "version": 4, "status": "saved"}
        conn.commit.assert_called_once()

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_found(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = {"code": "code v1", "version": 1, "description": "desc", "updated_at": "2024-01-01"}
        mock_get_conn.return_value = conn
        repo = SavedWidgetRepository()

        result = await repo.get("widget_1")

        assert result == {
            "widget_id": "widget_1",
            "code": "code v1",
            "version": 1,
            "description": "desc",
            "updated_at": "2024-01-01",
        }

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_missing(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = None
        mock_get_conn.return_value = conn
        repo = SavedWidgetRepository()

        result = await repo.get("widget_ghost")

        assert result is None

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_versions(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [{"version": 2, "description": "desc2", "created_at": "t2"}, {"version": 1, "description": "desc1", "created_at": "t1"}]
        mock_get_conn.return_value = conn
        repo = SavedWidgetRepository()

        result = await repo.get_versions("widget_1")

        assert result == [
            {"version": 2, "description": "desc2", "created_at": "t2"},
            {"version": 1, "description": "desc1", "created_at": "t1"},
        ]

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_by_version_found(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = {"code": "code v2", "description": "desc2", "created_at": "t2"}
        mock_get_conn.return_value = conn
        repo = SavedWidgetRepository()

        result = await repo.get_by_version("widget_1", 2)

        assert result == {
            "widget_id": "widget_1",
            "version": 2,
            "code": "code v2",
            "description": "desc2",
            "created_at": "t2",
        }

    @pytest.mark.anyio
    @patch("src.memory.repos.base.get_conn", new_callable=AsyncMock)
    async def test_get_by_version_missing(self, mock_get_conn, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = None
        mock_get_conn.return_value = conn
        repo = SavedWidgetRepository()

        result = await repo.get_by_version("widget_1", 99)

        assert result is None


class TestGetRepos:
    @pytest.mark.anyio
    async def test_get_repos_returns_all_seven_repos(self):
        repos = get_repos()
        assert isinstance(repos.messages, MessageRepository)
        assert isinstance(repos.sessions, SessionRepository)
        assert isinstance(repos.tool_calls, ToolCallRepository)
        assert isinstance(repos.widget_states, WidgetStateRepository)
        assert isinstance(repos.debug, DebugRepository)
        assert isinstance(repos.saved_widgets, SavedWidgetRepository)
        assert isinstance(repos.memory_index, MemoryIndexRepository)

    @pytest.mark.anyio
    async def test_get_repos_passes_connection(self, mock_conn):
        conn, cursor = mock_conn
        repos = get_repos(conn)
        assert repos.messages._conn is conn
        assert repos.sessions._conn is conn
        assert repos.tool_calls._conn is conn
        assert repos.widget_states._conn is conn
        assert repos.debug._conn is conn
        assert repos.saved_widgets._conn is conn
