import pytest

from src.memory.repos import (
    DebugRepository,
    MemoryIndexRepository,
    MessageRepository,
    SavedWidgetRepository,
    SessionRepository,
    ToolCallRepository,
    WidgetStateRepository,
    get_repos,
)


class TestSessionRepository:
    @pytest.mark.anyio
    async def test_ensure_creates_new(self, setup_test_db):
        repo = SessionRepository()
        await repo.ensure("sess_new")
        conn = await repo._get_conn()
        row = await (await conn.execute("SELECT * FROM sessions WHERE session_id = ?", ("sess_new",))).fetchone()
        assert row is not None
        assert row["session_id"] == "sess_new"

    @pytest.mark.anyio
    async def test_ensure_idempotent(self, setup_test_db):
        repo = SessionRepository()
        await repo.ensure("sess_1")
        await repo.ensure("sess_1")
        conn = await repo._get_conn()
        rows = await (await conn.execute("SELECT COUNT(*) as c FROM sessions WHERE session_id = ?", ("sess_1",))).fetchone()
        assert rows["c"] == 1

    @pytest.mark.anyio
    async def test_rename(self, setup_test_db):
        repo = SessionRepository()
        await repo.ensure("sess_1")
        await repo.rename("sess_1", "My Session")
        conn = await repo._get_conn()
        row = await (await conn.execute("SELECT name FROM sessions WHERE session_id = ?", ("sess_1",))).fetchone()
        assert row["name"] == "My Session"

    @pytest.mark.anyio
    async def test_delete(self, setup_test_db):
        repo = SessionRepository()
        await repo.ensure("sess_1")
        await repo.delete("sess_1")
        conn = await repo._get_conn()
        row = await (await conn.execute("SELECT * FROM sessions WHERE session_id = ?", ("sess_1",))).fetchone()
        assert row is None

    @pytest.mark.anyio
    async def test_get_all(self, setup_test_db):
        repo = SessionRepository()
        msgs = MessageRepository()
        await repo.ensure("s1")
        await repo.ensure("s2")
        await msgs.save("s1", "user", "hello", "m1")
        await msgs.save("s2", "user", "world", "m1")
        result = await repo.get_all(limit=10)
        assert len(result) >= 2
        sids = [r["session_id"] for r in result]
        assert "s1" in sids
        assert "s2" in sids

    @pytest.mark.anyio
    async def test_check_should_rename_true(self, setup_test_db):
        repo = SessionRepository()
        msgs = MessageRepository()
        await repo.ensure("sess_1")
        await msgs.save("sess_1", "user", "hello", "m1")
        assert await repo.check_should_rename("sess_1") is True

    @pytest.mark.anyio
    async def test_check_should_rename_false_named(self, setup_test_db):
        repo = SessionRepository()
        msgs = MessageRepository()
        await repo.ensure("sess_1")
        await repo.rename("sess_1", "Already Named")
        await msgs.save("sess_1", "user", "hello", "m1")
        assert await repo.check_should_rename("sess_1") is False

    @pytest.mark.anyio
    async def test_check_should_rename_false_multiple(self, setup_test_db):
        repo = SessionRepository()
        msgs = MessageRepository()
        await repo.ensure("sess_1")
        await msgs.save("sess_1", "user", "hello", "m1")
        await msgs.save("sess_1", "assistant", "hi", "m1")
        await msgs.save("sess_1", "user", "bye", "m1")
        assert await repo.check_should_rename("sess_1") is False

    @pytest.mark.anyio
    async def test_delete_cascade(self, setup_test_db):
        repos = get_repos()
        await repos.sessions.ensure("sess_cascade")
        await repos.messages.save("sess_cascade", "user", "hello", "m1")
        await repos.tool_calls.log("sess_cascade", "tool1", "{}", "ok")
        await repos.debug.save_info("sess_cascade", {"model": "m1"})
        await repos.widget_states.save_state("sess_cascade", "w1", "{}")
        await repos.memory_index.upsert("sess_cascade", "k1", "v1")
        await repos.sessions.delete_cascade("sess_cascade", repos)
        conn = await repos.sessions._get_conn()
        assert (await (await conn.execute("SELECT COUNT(*) as c FROM sessions WHERE session_id = ?", ("sess_cascade",))).fetchone())["c"] == 0
        assert (await (await conn.execute("SELECT COUNT(*) as c FROM messages WHERE session_id = ?", ("sess_cascade",))).fetchone())["c"] == 0
        assert (await (await conn.execute("SELECT COUNT(*) as c FROM tool_calls WHERE session_id = ?", ("sess_cascade",))).fetchone())["c"] == 0
        assert (await (await conn.execute("SELECT COUNT(*) as c FROM debug_info WHERE session_id = ?", ("sess_cascade",))).fetchone())["c"] == 0
        assert (await (await conn.execute("SELECT COUNT(*) as c FROM widget_states WHERE session_id = ?", ("sess_cascade",))).fetchone())["c"] == 0
        assert (await (await conn.execute("SELECT COUNT(*) as c FROM memory_index WHERE session_id = ?", ("sess_cascade",))).fetchone())["c"] == 0



class TestMessageRepository:
    @pytest.mark.anyio
    async def test_save_and_get(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MessageRepository()
        await repo.save("sess_1", "user", "hello", "model-x")
        await repo.save("sess_1", "assistant", "hi there", "model-x")
        msgs = await repo.get_session_messages("sess_1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "hi there"

    @pytest.mark.anyio
    async def test_save_none_content_becomes_empty(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MessageRepository()
        await repo.save("sess_1", "assistant", None, "model-x")
        msgs = await repo.get_session_messages("sess_1")
        assert len(msgs) == 1
        assert msgs[0]["content"] == ""

    @pytest.mark.anyio
    async def test_save_record(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MessageRepository()
        from src.memory.repos import MessageRecord
        record = MessageRecord(
            session_id="sess_1",
            role="user",
            content="via record",
            model="m1",
            reasoning="thinking",
            phases='["p1"]',
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        await repo.save_record(record)
        msgs = await repo.get_session_messages("sess_1")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "via record"
        assert msgs[0]["reasoning"] == "thinking"

    @pytest.mark.anyio
    async def test_get_empty_session(self, setup_test_db):
        repo = MessageRepository()
        msgs = await repo.get_session_messages("nonexistent")
        assert msgs == []

    @pytest.mark.anyio
    async def test_delete_empty_assistant(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MessageRepository()
        await repo.save("sess_1", "user", "hello", "m1")
        await repo.save("sess_1", "assistant", "", "m1")
        await repo.save("sess_1", "assistant", "real response", "m1")
        await repo.delete_empty_assistant("sess_1")
        msgs = await repo.get_session_messages("sess_1")
        assert len(msgs) == 2
        assert all(m["content"] != "" for m in msgs)


class TestToolCallRepository:
    @pytest.mark.anyio
    async def test_log_and_get_history(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = ToolCallRepository()
        await repo.log("sess_1", "get_weather", '{"city":"NYC"}', "success", turn=1)
        await repo.log("sess_1", "search", '{"q":"test"}', "error", turn=2)
        history = await repo.get_history("sess_1", limit=10)
        assert len(history) == 2
        assert history[0]["tool_name"] == "search"
        assert history[0]["status"] == "error"
        assert history[1]["tool_name"] == "get_weather"

    @pytest.mark.anyio
    async def test_get_history_limit(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = ToolCallRepository()
        for i in range(5):
            await repo.log("sess_1", f"tool_{i}", "{}", "ok", turn=i)
        history = await repo.get_history("sess_1", limit=3)
        assert len(history) == 3

    @pytest.mark.anyio
    async def test_record_execution(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = ToolCallRepository()
        await repo.record_execution(
            "sess_1", "tool_x", '{"a":1}', "success", "result data",
            turn=1, tool_call_id="call_1"
        )
        history = await repo.get_history("sess_1")
        assert len(history) == 1
        assert history[0]["tool_name"] == "tool_x"
        msgs = await MessageRepository().get_session_messages("sess_1")
        tool_msgs = [m for m in msgs if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"] == "result data"

    @pytest.mark.anyio
    async def test_get_history_empty(self, setup_test_db):
        repo = ToolCallRepository()
        history = await repo.get_history("nonexistent")
        assert history == []


class TestDebugRepository:
    @pytest.mark.anyio
    async def test_save_and_get_info(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = DebugRepository()
        data = {
            "model": "gpt-4",
            "reasoning": "thinking hard",
            "system_prompt": "you are helpful",
            "tool_calls": [{"name": "web_search"}],
            "history_before": [{"role": "user", "content": "hi"}],
            "asr_telemetry": [{"transport": "ws"}],
        }
        await repo.save_info("sess_1", data)
        result = await repo.get_info("sess_1")
        assert result["model"] == "gpt-4"
        assert result["reasoning"] == "thinking hard"
        assert result["system_prompt"] == "you are helpful"
        assert result["tool_calls"] == [{"name": "web_search"}]
        assert result["history_before"] == [{"role": "user", "content": "hi"}]
        assert result["asr_telemetry"] == [{"transport": "ws"}]

    @pytest.mark.anyio
    async def test_get_info_missing(self, setup_test_db):
        repo = DebugRepository()
        result = await repo.get_info("nonexistent")
        assert result == {}

    @pytest.mark.anyio
    async def test_save_info_overwrite(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = DebugRepository()
        await repo.save_info("sess_1", {"model": "v1"})
        await repo.save_info("sess_1", {"model": "v2"})
        result = await repo.get_info("sess_1")
        assert result["model"] == "v2"


class TestWidgetStateRepository:
    @pytest.mark.anyio
    async def test_save_and_get_states(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = WidgetStateRepository()
        await repo.save_state("sess_1", "w1", '{"x": 1}')
        await repo.save_state("sess_1", "w2", '{"y": 2}')
        states = await repo.get_states("sess_1")
        assert states == {"w1": '{"x": 1}', "w2": '{"y": 2}'}

    @pytest.mark.anyio
    async def test_save_upsert(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = WidgetStateRepository()
        await repo.save_state("sess_1", "w1", '{"v": 1}')
        await repo.save_state("sess_1", "w1", '{"v": 2}')
        states = await repo.get_states("sess_1")
        assert states["w1"] == '{"v": 2}'
        assert len(states) == 1

    @pytest.mark.anyio
    async def test_get_states_empty(self, setup_test_db):
        repo = WidgetStateRepository()
        states = await repo.get_states("nonexistent")
        assert states == {}


class TestSavedWidgetRepository:
    @pytest.mark.anyio
    async def test_save_and_get(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = SavedWidgetRepository()
        result = await repo.save("sess_1", "widget_1", "console.log('hi')", "initial")
        assert result["widget_id"] == "widget_1"
        assert result["version"] == 1
        assert result["status"] == "saved"
        widget = await repo.get("widget_1")
        assert widget is not None
        assert widget["code"] == "console.log('hi')"
        assert widget["version"] == 1

    @pytest.mark.anyio
    async def test_save_increments_version(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = SavedWidgetRepository()
        await repo.save("sess_1", "w1", "code v1", "v1")
        await repo.save("sess_1", "w1", "code v2", "v2")
        widget = await repo.get("w1")
        assert widget["version"] == 2
        assert widget["code"] == "code v2"

    @pytest.mark.anyio
    async def test_get_missing(self, setup_test_db):
        repo = SavedWidgetRepository()
        assert await repo.get("nonexistent") is None

    @pytest.mark.anyio
    async def test_get_versions(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = SavedWidgetRepository()
        await repo.save("sess_1", "w1", "v1", "first")
        await repo.save("sess_1", "w1", "v2", "second")
        await repo.save("sess_1", "w1", "v3", "third")
        versions = await repo.get_versions("w1")
        assert len(versions) == 3
        assert versions[0]["version"] == 3
        assert versions[0]["description"] == "third"

    @pytest.mark.anyio
    async def test_delete_by_session(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = SavedWidgetRepository()
        await repo.save("sess_1", "w1", "code", "desc")
        await repo.delete_by_session("sess_1")
        assert await repo.get("w1") is None
        versions = await repo.get_versions("w1")
        assert len(versions) == 0


class TestMemoryIndexRepository:
    @pytest.mark.anyio
    async def test_upsert_and_get(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MemoryIndexRepository()
        await repo.upsert("sess_1", "user:interests", "coding, music")
        result = await repo.get("sess_1", "user:interests")
        assert result == "coding, music"

    @pytest.mark.anyio
    async def test_upsert_overwrite(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MemoryIndexRepository()
        await repo.upsert("sess_1", "k1", "old value")
        await repo.upsert("sess_1", "k1", "new value")
        result = await repo.get("sess_1", "k1")
        assert result == "new value"

    @pytest.mark.anyio
    async def test_get_missing(self, setup_test_db):
        repo = MemoryIndexRepository()
        assert await repo.get("nonexistent", "k1") is None

    @pytest.mark.anyio
    async def test_get_all(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MemoryIndexRepository()
        await repo.upsert("sess_1", "k1", "v1")
        await repo.upsert("sess_1", "k2", "v2")
        await repo.upsert("sess_1", "k3", "v3")
        all_entries = await repo.get_all("sess_1")
        assert len(all_entries) == 3
        keys = [e["key"] for e in all_entries]
        assert keys == ["k1", "k2", "k3"]

    @pytest.mark.anyio
    async def test_delete(self, setup_test_db):
        await SessionRepository().ensure("sess_1")
        repo = MemoryIndexRepository()
        await repo.upsert("sess_1", "k1", "v1")
        await repo.delete("sess_1", "k1")
        assert await repo.get("sess_1", "k1") is None
