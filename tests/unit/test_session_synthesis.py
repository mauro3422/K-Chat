import json
import sqlite3
from datetime import date

import pytest

from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.synthesis.daily import (
    generate_daily_synthesis,
    get_session_stats,
    get_sessions_for_date,
)
from src.memory.synthesis.session import (
    candidates_from_session_summary_artifact,
    discover_session_summary_artifacts,
    generate_session_summaries,
    generate_session_summary_candidates,
    get_session_messages_for_summary,
    get_sessions_for_summary_date,
    _is_test_session_id,
    load_session_summary_previews,
    session_summary_candidate_path,
    session_summary_path,
    vectorize_session_summary_artifacts,
)


@pytest.mark.parametrize(
    ("session_id", "expected"),
    [
        ("test-123", True),
        ("test_session", True),
        ("smoke-test-session", True),
        ("contest-planning", False),
        ("latest-memory-review", False),
    ],
)
def test_is_test_session_id_uses_explicit_prefixes(session_id, expected):
    assert _is_test_session_id(session_id) is expected


class _SummaryStore:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE vec_meta (
                rowid INTEGER PRIMARY KEY,
                source TEXT,
                source_key TEXT,
                exchange_idx INTEGER,
                text TEXT,
                hash TEXT,
                content_hash TEXT,
                source_node_id TEXT DEFAULT ''
            )
            """
        )
        self.inserted: list[dict] = []

    def _get_conn(self):
        return self.conn

    def insert(self, _embedding, **kwargs) -> int:
        rowid = 10 + len(self.inserted)
        self.inserted.append(kwargs)
        self.conn.execute(
            """
            INSERT INTO vec_meta (
                rowid, source, source_key, exchange_idx, text, hash, content_hash, source_node_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                kwargs["source"],
                kwargs["source_key"],
                kwargs["exchange_idx"],
                kwargs["text"],
                kwargs["hash"],
                kwargs["content_hash"],
                kwargs.get("source_node_id", ""),
            ),
        )
        self.conn.commit()
        return rowid

    def close(self) -> None:
        self.conn.close()


def _insert_session(db_path: str, session_id: str = "s1") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO sessions (session_id, name, created_at) VALUES (?, ?, ?)",
            (session_id, "Memory planning", "2026-07-02T08:00:00"),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, "user", "Quiero memoria por capas con inbox y embeddings.", "2026-07-02T08:01:00"),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, "assistant", "Armamos un plan con curadores y candidatos.", "2026-07-02T08:02:00"),
        )
        conn.commit()
    finally:
        conn.close()


def _create_session_db_with_channel_columns(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                name TEXT,
                created_at TEXT,
                channel TEXT,
                source_channel TEXT,
                source TEXT,
                telegram_chat_id INTEGER
            )
            """
        )
        conn.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created_at TEXT)"
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                session_id, name, created_at, channel, source_channel, source, telegram_chat_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("web-1", "Web", "2026-07-02T08:00:00", "web", "", "", None),
                ("tg-1", "Telegram explicit", "2026-07-02T09:00:00", "telegram", "", "", None),
                ("cli-1", "CLI source channel", "2026-07-02T10:00:00", "", "cli", "", None),
                ("tg-2", "Telegram legacy", "2026-07-02T11:00:00", "", "", "", 123),
            ],
        )
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [
                ("web-1", "system", "Channel activity.", "2026-07-02T08:00:01"),
                ("tg-1", "system", "Channel activity.", "2026-07-02T09:00:01"),
                ("cli-1", "system", "Channel activity.", "2026-07-02T10:00:01"),
                ("tg-2", "system", "Channel activity.", "2026-07-02T11:00:01"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_daily_memory_tables(memory_db_path: str) -> None:
    conn = sqlite3.connect(memory_db_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS vec_meta (source TEXT, source_key TEXT, created_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS memory_index (key TEXT, value TEXT, created_at TEXT)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS entities (id TEXT, name TEXT, entity_type TEXT, mention_count INTEGER, first_seen TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS topic_clusters (cluster_id TEXT, label TEXT, keywords TEXT, session_count INTEGER, exchange_count INTEGER, weight REAL, first_seen TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS exchange_clusters (cluster_id TEXT, exchange_rowid INTEGER)"
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.anyio
async def test_generate_session_summaries_writes_idempotent_artifact(setup_test_db, tmp_path):
    _insert_session(setup_test_db)

    first = await generate_session_summaries(setup_test_db, root=tmp_path, target_date=date(2026, 7, 2))
    second = await generate_session_summaries(setup_test_db, root=tmp_path, target_date=date(2026, 7, 2))

    path = session_summary_path("s1", root=tmp_path, target=date(2026, 7, 2))
    text = path.read_text(encoding="utf-8")
    assert first[0]["changed"] is True
    assert second[0]["changed"] is False
    assert "Session Summary - Memory planning" in text
    assert "inbox" in text
    assert "content_hash" in text


@pytest.mark.anyio
async def test_generate_session_summaries_skips_test_and_single_message_sessions(
    setup_test_db,
    tmp_path,
    monkeypatch,
):
    _insert_session(setup_test_db, "test-123")
    _insert_session(setup_test_db, "contest-planning")
    conn = sqlite3.connect(setup_test_db)
    try:
        conn.execute(
            "INSERT INTO sessions (session_id, name, created_at) VALUES (?, ?, ?)",
            ("short-session", "Short", "2026-07-02T09:00:00"),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            ("short-session", "user", "Solo un mensaje.", "2026-07-02T09:01:00"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    results = await generate_session_summaries(
        setup_test_db,
        root=tmp_path,
        target_date=date(2026, 7, 2),
    )

    assert [item["session_id"] for item in results] == ["contest-planning"]
    assert session_summary_path(
        "contest-planning",
        root=tmp_path,
        target=date(2026, 7, 2),
    ).exists()


@pytest.mark.anyio
async def test_get_sessions_for_summary_date_prefers_explicit_channel_metadata(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    _create_session_db_with_channel_columns(db_path)

    sessions = await get_sessions_for_summary_date(db_path, "2026-07-02")

    channels = {item["session_id"]: item["channel"] for item in sessions}
    assert channels == {
        "web-1": "web",
        "tg-1": "telegram",
        "cli-1": "cli",
        "tg-2": "telegram",
    }


@pytest.mark.anyio
async def test_daily_queries_use_message_activity_date_for_long_lived_session(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO sessions VALUES ('s1', 'Long lived', '2026-07-02T08:00:00')"
        )
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [
                ("s1", "user", "Mensaje del día inicial.", "2026-07-02T08:01:00"),
                ("s1", "assistant", "Respuesta inicial.", "2026-07-02T08:02:00"),
                ("s1", "user", "Actividad de otro día.", "2026-07-18T09:01:00"),
                ("s1", "assistant", "Respuesta del otro día.", "2026-07-18T09:02:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    daily_sessions = await get_sessions_for_date(db_path, "2026-07-18")
    summary_sessions = await get_sessions_for_summary_date(db_path, "2026-07-18")
    stats = await get_session_stats(db_path, "s1", "2026-07-18")
    messages = await get_session_messages_for_summary(
        db_path,
        "s1",
        date_str="2026-07-18",
    )

    assert [item["session_id"] for item in daily_sessions] == ["s1"]
    assert [item["session_id"] for item in summary_sessions] == ["s1"]
    assert stats["message_count"] == 2
    assert [item["content"] for item in messages] == [
        "Actividad de otro día.",
        "Respuesta del otro día.",
    ]


@pytest.mark.anyio
async def test_generate_session_summaries_writes_channel_namespaced_artifacts(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    _create_session_db_with_channel_columns(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [
                ("web-1", "user", "Web session message.", "2026-07-02T08:01:00"),
                ("web-1", "assistant", "Sure, what do you need?", "2026-07-02T08:01:05"),
                ("tg-1", "user", "Telegram tambien debe entrar al pipeline de memoria.", "2026-07-02T09:01:00"),
                ("tg-1", "assistant", "Noted, Telegram channel test.", "2026-07-02T09:01:05"),
                ("cli-1", "user", "CLI session message.", "2026-07-02T10:01:00"),
                ("cli-1", "assistant", "Running CLI.", "2026-07-02T10:01:05"),
                ("tg-2", "user", "Telegram legacy session.", "2026-07-02T11:01:00"),
                ("tg-2", "assistant", "Legacy connection established.", "2026-07-02T11:01:05"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    result = await generate_session_summaries(db_path, root=tmp_path, target_date=date(2026, 7, 2))

    by_id = {item["session_id"]: item for item in result}
    telegram_path = session_summary_path("tg-1", channel="telegram", root=tmp_path, target=date(2026, 7, 2))
    assert by_id["tg-1"]["channel"] == "telegram"
    assert by_id["cli-1"]["channel"] == "cli"
    assert by_id["web-1"]["channel"] == "web"
    assert by_id["tg-2"]["channel"] == "telegram"
    assert telegram_path.exists()
    assert "- Channel: telegram" in telegram_path.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_daily_synthesis_consumes_session_summary(setup_test_db, tmp_path, monkeypatch):
    _insert_session(setup_test_db)
    memory_db = tmp_path / "memory.db"
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", str(memory_db))
    _ensure_daily_memory_tables(str(memory_db))
    await generate_session_summaries(setup_test_db, root=tmp_path, target_date=date(2026, 7, 2))

    report = await generate_daily_synthesis(
        setup_test_db,
        target_date=date(2026, 7, 2),
        root=tmp_path,
    )

    text = open(report, encoding="utf-8").read()
    assert "Session Summary Previews" in text
    assert "Summary artifact" in text
    assert "Memory planning" in text


def test_load_session_summary_previews_returns_existing_artifacts(tmp_path):
    path = session_summary_path("s1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '<!-- metadata: {"session_id": "s1", "channel": "web"} -->\n# Session Summary - Demo\n\n- line\n',
        encoding="utf-8",
    )

    previews = load_session_summary_previews(["s1"], root=tmp_path)

    assert previews["s1"]["path"] == str(path)
    assert previews["s1"]["metadata"]["channel"] == "web"


@pytest.mark.anyio
async def test_vectorize_session_summary_artifacts_embeds_and_marks_catalog(tmp_path, monkeypatch):
    path = session_summary_path("s1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '<!-- metadata: {"session_id": "s1", "channel": "web"} -->\n'
        "# Session Summary - Demo\n\n- Mauro habla de memoria por capas.\n",
        encoding="utf-8",
    )
    store = _SummaryStore()
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts: [[0.1] * 384 for _ in texts],
    )

    try:
        result = await vectorize_session_summary_artifacts(
            root=tmp_path,
            store=store,
            catalog=catalog,
            source_node_id="pc",
        )
    finally:
        store.close()

    row = catalog.get(source="session_summary", source_key="s1", item_idx=-1)
    assert result == {"artifacts": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}
    assert row is not None
    assert row["status"] == "embedded"
    assert row["pipeline"] == "session_summary_embedding"
    assert row["source_node_id"] == "pc"


@pytest.mark.anyio
async def test_vectorize_session_summary_artifacts_skips_unchanged(tmp_path, monkeypatch):
    path = session_summary_path("s1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '<!-- metadata: {"session_id": "s1", "channel": "web"} -->\n# Session Summary - Demo\n',
        encoding="utf-8",
    )
    store = _SummaryStore()
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts: [[0.1] * 384 for _ in texts],
    )

    try:
        first = await vectorize_session_summary_artifacts(root=tmp_path, store=store, catalog=catalog)
        second = await vectorize_session_summary_artifacts(root=tmp_path, store=store, catalog=catalog)
    finally:
        store.close()

    assert first["embedded"] == 1
    assert second["unchanged"] == 1
    assert second["embedded"] == 0


def test_discover_session_summary_artifacts_reads_metadata(tmp_path):
    path = session_summary_path("s1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '<!-- metadata: {"session_id": "s1", "channel": "telegram"} -->\n# Session Summary - Demo\n',
        encoding="utf-8",
    )

    artifacts = discover_session_summary_artifacts(root=tmp_path)

    assert artifacts[0]["session_id"] == "s1"
    assert artifacts[0]["channel"] == "telegram"
    assert artifacts[0]["content_hash"]


def test_candidates_from_session_summary_artifact_extracts_memory_signals(tmp_path):
    path = session_summary_path("s1", root=tmp_path)
    artifact = {
        "session_id": "s1",
        "channel": "web",
        "path": str(path),
        "content_hash": "hash-1",
        "text": "# Session Summary\n\n- Mauro quiere memoria por capas con embeddings.\n- Charla casual.",
    }

    candidates = candidates_from_session_summary_artifact(artifact, timestamp="2026-07-02T10:00:00")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["source"] == "session_summary"
    assert candidate["session_id"] == "s1"
    assert candidate["status"] == "pending"
    assert candidate["relation_type"] == "DERIVED_FROM"
    assert candidate["source_id"].startswith("candidate:")
    assert candidate["target_id"] == "session:s1"
    assert candidate["temporal"]["first_seen"] == "2026-07-02T10:00:00"
    assert candidate["provenance"]["session_id"] == "s1"
    assert {entity["name"] for entity in candidate["entities"]} >= {"Mauro", "memoria", "embedding"}
    assert any(relation["relation_type"] == "MENTIONS" for relation in candidate["proposed_relations"])
    assert "memoria por capas" in candidate["query"]


def test_candidates_from_session_summary_artifact_detects_relation_intents(tmp_path):
    base = {
        "session_id": "s1",
        "channel": "web",
        "path": str(session_summary_path("s1", root=tmp_path)),
        "content_hash": "hash-1",
    }
    cases = [
        ("- Esto contradice una memoria canonica previa sobre Kairos.", "CONTRADICTS", "memory:canonical"),
        ("- Mauro quiere refinar metadata de memoria y curaduria.", "REFINES", "memory:canonical"),
        ("- Hay que conectar memoria transversal con embeddings semanticos.", "LINKS_TO", "memory:semantic-neighbor"),
    ]

    for text, relation_type, target_id in cases:
        candidates = candidates_from_session_summary_artifact({**base, "text": text}, timestamp="2026-07-02T10:00:00")

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate["relation_type"] == relation_type
        assert candidate["target_id"] == target_id
        assert candidate["target_needs_resolution"] is True
        assert any(relation["relation_type"] == "DERIVED_FROM" for relation in candidate["proposed_relations"])
        assert any(relation["relation_type"] == relation_type for relation in candidate["proposed_relations"])


def test_generate_session_summary_candidates_writes_idempotent_jsonl(tmp_path):
    path = session_summary_path("s1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '<!-- metadata: {"session_id": "s1", "channel": "web"} -->\n'
        "# Session Summary - Demo\n\n- Mauro quiere memoria por capas con embeddings.\n",
        encoding="utf-8",
    )

    first = generate_session_summary_candidates(
        root=tmp_path,
        target_date=date(2026, 7, 2),
        timestamp="2026-07-02T10:00:00",
    )
    second = generate_session_summary_candidates(
        root=tmp_path,
        target_date=date(2026, 7, 2),
        timestamp="2026-07-02T10:00:00",
    )
    candidate_path = session_summary_candidate_path(date(2026, 7, 2), root=tmp_path)
    rows = [json.loads(line) for line in candidate_path.read_text(encoding="utf-8").splitlines()]

    assert first["created"] == 1
    assert first["total"] == 1
    assert second["created"] == 0
    assert rows[0]["type"] == "session_summary_candidate"
    assert rows[0]["source_artifact"] == str(path)
    assert rows[0]["source_id"].startswith("candidate:")
    assert rows[0]["target_id"] == "session:s1"
    assert rows[0]["proposed_relations"]
    assert rows[0]["promotion_decision"] in {"hold", "review"}
    assert rows[0]["promotion_decision"] != "auto_promote"


def test_generate_session_candidates_reuses_pending_id_across_daily_partitions(tmp_path):
    path = session_summary_path("s1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '<!-- metadata: {"session_id": "s1", "channel": "web"} -->\n'
        "# Session Summary - Demo\n\n- Mauro quiere memoria por capas con embeddings.\n",
        encoding="utf-8",
    )

    first = generate_session_summary_candidates(
        root=tmp_path,
        target_date=date(2026, 7, 2),
        timestamp="2026-07-02T10:00:00",
    )
    second = generate_session_summary_candidates(
        root=tmp_path,
        target_date=date(2026, 7, 3),
        timestamp="2026-07-03T10:00:00",
    )

    first_path = session_summary_candidate_path(date(2026, 7, 2), root=tmp_path)
    second_path = session_summary_candidate_path(date(2026, 7, 3), root=tmp_path)
    saved = json.loads(first_path.read_text(encoding="utf-8").splitlines()[0])

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["reused"] == 1
    assert second["total"] == 0
    assert second_path.exists() is False
    assert saved["lifecycle"]["observation_count"] == 2
    assert saved["lifecycle"]["age_days"] == 1
    assert saved["temporal"]["last_seen"] == "2026-07-03T10:00:00"
