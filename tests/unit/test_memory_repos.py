import pytest
import pytest_asyncio

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
        async with repo._connection() as conn:
            row = await (await conn.execute("SELECT * FROM sessions WHERE session_id = ?", ("sess_new",))).fetchone()
        assert row is not None
        assert row["session_id"] == "sess_new"

    @pytest.mark.anyio
    async def test_ensure_idempotent(self, setup_test_db):
        repo = SessionRepository()
        await repo.ensure("sess_1")
        await repo.ensure("sess_1")
        async with repo._connection() as conn:
            rows = await (await conn.execute("SELECT COUNT(*) as c FROM sessions WHERE session_id = ?", ("sess_1",))).fetchone()
        assert rows["c"] == 1

    @pytest.mark.anyio
    async def test_rename(self, setup_test_db):
        repo = SessionRepository()
        await repo.ensure("sess_1")
        await repo.rename("sess_1", "My Session")
        async with repo._connection() as conn:
            row = await (await conn.execute("SELECT name FROM sessions WHERE session_id = ?", ("sess_1",))).fetchone()
        assert row["name"] == "My Session"

    @pytest.mark.anyio
    async def test_delete(self, setup_test_db):
        repo = SessionRepository()
        await repo.ensure("sess_1")
        await repo.delete("sess_1")
        async with repo._connection() as conn:
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
        async with repos.sessions._connection() as conn:
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


_MEMORY_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS memory_index (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        metadata TEXT DEFAULT '{}',
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        mention_count INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS entity_relations (
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        weight REAL DEFAULT 1.0,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        PRIMARY KEY (source_id, target_id, relation_type)
    )""",
    """CREATE TABLE IF NOT EXISTS entity_mentions (
        entity_id TEXT NOT NULL,
        exchange_rowid INTEGER NOT NULL,
        session_id TEXT NOT NULL DEFAULT '',
        first_seen TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (entity_id, exchange_rowid)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_entities_name ON entities (name)",
    "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities (entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_entity_relations_target ON entity_relations (target_id)",
    "CREATE INDEX IF NOT EXISTS idx_entity_mentions_exchange ON entity_mentions (exchange_rowid)",
    "CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity ON entity_mentions (entity_id)",
]


@pytest_asyncio.fixture
async def memory_db_conn():
    import aiosqlite

    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    for stmt in _MEMORY_SCHEMA:
        await conn.execute(stmt)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
def global_index_repo(memory_db_conn):
    from src.memory.repos_memory.memory_index_repo import GlobalMemoryIndexRepository

    return GlobalMemoryIndexRepository(conn=memory_db_conn)


@pytest.fixture
def entity_repo(memory_db_conn):
    from src.memory.repos_memory.entity_repo import EntityRepository

    return EntityRepository(conn=memory_db_conn)


class TestGlobalMemoryIndexRepository:
    @pytest.mark.anyio
    async def test_upsert_and_get(self, global_index_repo):
        await global_index_repo.upsert("user:interests", "coding, music")
        result = await global_index_repo.get("user:interests")
        assert result == "coding, music"

    @pytest.mark.anyio
    async def test_upsert_overwrite(self, global_index_repo):
        await global_index_repo.upsert("k1", "old value")
        await global_index_repo.upsert("k1", "new value")
        result = await global_index_repo.get("k1")
        assert result == "new value"

    @pytest.mark.anyio
    async def test_get_nonexistent(self, global_index_repo):
        result = await global_index_repo.get("nonexistent")
        assert result is None

    @pytest.mark.anyio
    async def test_delete(self, global_index_repo):
        await global_index_repo.upsert("k1", "v1")
        await global_index_repo.delete("k1")
        assert await global_index_repo.get("k1") is None

    @pytest.mark.anyio
    async def test_get_all(self, global_index_repo):
        await global_index_repo.upsert("k1", "v1")
        await global_index_repo.upsert("k2", "v2")
        all_entries = await global_index_repo.get_all()
        assert len(all_entries) == 2
        keys = [e["key"] for e in all_entries]
        assert keys == ["k1", "k2"]

    @pytest.mark.anyio
    async def test_get_all_empty(self, global_index_repo):
        assert await global_index_repo.get_all() == []

    @pytest.mark.anyio
    async def test_search(self, global_index_repo):
        await global_index_repo.upsert("user:name", "Mauro")
        await global_index_repo.upsert("user:stack", "Python, Rust")
        results = await global_index_repo.search("Mauro")
        assert len(results) == 1
        assert results[0]["key"] == "user:name"

    @pytest.mark.anyio
    async def test_count(self, global_index_repo):
        assert await global_index_repo.count() == 0
        await global_index_repo.upsert("k1", "v1")
        await global_index_repo.upsert("k2", "v2")
        assert await global_index_repo.count() == 2


class TestEntityRepository:
    @pytest.mark.anyio
    async def test_upsert_entity(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1",
            "Python",
            "tecnologia",
            metadata={"type": "language"},
            timestamp="2024-01-01",
        )
        entity = await entity_repo.get_entity("e1")
        assert entity is not None
        assert entity["name"] == "Python"
        assert entity["entity_type"] == "tecnologia"
        assert entity["mention_count"] == 1

    @pytest.mark.anyio
    async def test_upsert_entity_update(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-02"
        )
        entity = await entity_repo.get_entity("e1")
        assert entity["mention_count"] == 2
        assert entity["last_seen"] == "2024-01-02"

    @pytest.mark.anyio
    async def test_get_entity(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        entity = await entity_repo.get_entity("e1")
        assert entity is not None
        assert entity["id"] == "e1"

    @pytest.mark.anyio
    async def test_get_entity_nonexistent(self, entity_repo):
        assert await entity_repo.get_entity("nonexistent") is None

    @pytest.mark.anyio
    async def test_get_entity_by_name(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        entity = await entity_repo.get_entity_by_name("Python", "tecnologia")
        assert entity is not None
        assert entity["id"] == "e1"

    @pytest.mark.anyio
    async def test_get_entity_by_name_nonexistent(self, entity_repo):
        entity = await entity_repo.get_entity_by_name("Nope", "unknown")
        assert entity is None

    @pytest.mark.anyio
    async def test_search_entities(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_entity(
            "e2", "Rust", "tecnologia", timestamp="2024-01-01"
        )
        results = await entity_repo.search_entities("Python")
        assert len(results) == 1
        assert results[0]["name"] == "Python"

    @pytest.mark.anyio
    async def test_search_entities_by_type(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_entity(
            "e2", "Mauro", "persona", timestamp="2024-01-01"
        )
        results = await entity_repo.search_entities("P", entity_type="tecnologia")
        assert len(results) == 1
        assert results[0]["name"] == "Python"

    @pytest.mark.anyio
    async def test_upsert_relation(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_entity(
            "e2", "FastAPI", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_relation("e1", "e2", "used_by", 0.8, "2024-01-01")

    @pytest.mark.anyio
    async def test_explore_graph(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_entity(
            "e2", "FastAPI", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_entity(
            "e3", "Django", "tecnologia", timestamp="2024-01-01"
        )
        await entity_repo.upsert_relation("e1", "e2", "used_by", 0.8, "2024-01-01")
        await entity_repo.upsert_relation("e1", "e3", "used_by", 0.6, "2024-01-01")
        result = await entity_repo.explore_graph("e1", depth=1)
        names = {r["name"] for r in result}
        assert "FastAPI" in names or "Django" in names
        assert "Python" not in names

    @pytest.mark.anyio
    async def test_explore_graph_nonexistent(self, entity_repo):
        result = await entity_repo.explore_graph("nonexistent", depth=2)
        assert result == []

    @pytest.mark.anyio
    async def test_count(self, entity_repo):
        assert await entity_repo.count() == 0
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        assert await entity_repo.count() == 1

    @pytest.mark.anyio
    async def test_delete(self, entity_repo):
        await entity_repo.upsert_entity(
            "e1", "Python", "tecnologia", timestamp="2024-01-01"
        )
        assert await entity_repo.delete("e1") is True
        assert await entity_repo.get_entity("e1") is None

    @pytest.mark.anyio
    async def test_delete_nonexistent(self, entity_repo):
        assert await entity_repo.delete("nonexistent") is False


class TestFlushRelationsToDb:
    @pytest.mark.anyio
    async def test_flush_relations_skips_integrity_error(self, in_memory_db, caplog):
        import os
        import tempfile
        import aiosqlite
        from src.memory.entity.linker import EntityLinker, EntityRelation, flush_relations_to_db

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = tmp.name
        tmp.close()

        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute("PRAGMA foreign_keys=ON")
                await db.execute("""CREATE TABLE entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    mention_count INTEGER DEFAULT 1
                )""")
                await db.execute("""CREATE TABLE entity_relations (
                    source_id TEXT NOT NULL REFERENCES entities(id),
                    target_id TEXT NOT NULL REFERENCES entities(id),
                    relation_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, relation_type)
                )""")
                await db.commit()

            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO entities (id, name, entity_type, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                    ("e1", "Entity1", "test_type", "2024-01-01", "2024-01-01"),
                )
                await db.execute(
                    "INSERT INTO entities (id, name, entity_type, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                    ("e2", "Entity2", "test_type", "2024-01-01", "2024-01-01"),
                )
                await db.commit()

            linker = EntityLinker()
            linker._relations[("e1", "e2", "co_occurrence")] = EntityRelation(
                source_id="e1", target_id="e2", relation_type="co_occurrence",
                weight=1.0, first_seen="2024-01-01", last_seen="2024-01-01",
            )
            linker._relations[("nonexistent", "e2", "co_occurrence")] = EntityRelation(
                source_id="nonexistent", target_id="e2", relation_type="co_occurrence",
                weight=1.0, first_seen="2024-01-01", last_seen="2024-01-01",
            )

            caplog.set_level("WARNING", logger="src.memory.entity.linker")
            count = await flush_relations_to_db(linker, db_path)

            assert count == 1
            assert "Skipping entity relation with missing entity" in caplog.text

            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute("SELECT COUNT(*) as c FROM entity_relations")
                row = await cursor.fetchone()
                assert row[0] == 1

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
