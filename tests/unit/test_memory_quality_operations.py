import sqlite3

import pytest

from src.memory.operations import quality


def _create_memory_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE entities (
                id TEXT PRIMARY KEY, name TEXT, entity_type TEXT,
                mention_count INTEGER DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE entity_relations (
                source_id TEXT, target_id TEXT, relation_type TEXT, weight REAL
            )"""
        )
        conn.execute("CREATE TABLE entity_mentions (entity_id TEXT)")
        conn.execute(
            "CREATE TABLE memory_curated_relations (source_id TEXT, target_id TEXT)"
        )
        conn.execute(
            """CREATE TABLE topic_clusters (
                cluster_id TEXT, keywords TEXT, weight REAL
            )"""
        )
        conn.execute(
            """CREATE TABLE topic_relations (
                source_id TEXT, target_id TEXT, shared_keywords TEXT,
                shared_count INTEGER, relationship_type TEXT, weight REAL,
                created_at TEXT
            )"""
        )


def _create_sessions_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT)"
        )
        conn.execute(
            "CREATE TABLE tool_calls (id INTEGER PRIMARY KEY, session_id TEXT)"
        )
        conn.execute("CREATE TABLE debug_info (session_id TEXT PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE chat_journal (id INTEGER PRIMARY KEY, session_id TEXT)"
        )


@pytest.mark.anyio
async def test_prune_entities_removes_only_unreferenced_generated_leaf(
    tmp_path,
    monkeypatch,
):
    memory_db = str(tmp_path / "memory.db")
    sessions_db = str(tmp_path / "sessions.db")
    _create_memory_db(memory_db)
    _create_sessions_db(sessions_db)
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", memory_db)
    monkeypatch.setenv("SESSIONS_DB_PATH", sessions_db)
    monkeypatch.setattr(
        quality,
        "_backup_connection",
        lambda *_args, **_kwargs: str(tmp_path / "backup.db"),
    )
    with sqlite3.connect(memory_db) as conn:
        conn.executemany(
            "INSERT INTO entities VALUES (?, ?, ?, ?)",
            [
                ("pmi_noise", "noise", "concept", 1),
                ("person:mauro", "Mauro", "persona", 5),
            ],
        )
        conn.execute(
            "INSERT INTO entity_relations VALUES ('pmi_noise', 'person:mauro', 'co_occurrence', 0.2)"
        )

    preview = await quality._prune_entities(dry_run=True)
    applied = await quality._prune_entities(dry_run=False, confirm=True)

    assert "1 entidades" in preview
    assert "Podadas 1 entidades" in applied
    with sqlite3.connect(memory_db) as conn:
        assert conn.execute("SELECT id FROM entities").fetchall() == [
            ("person:mauro",)
        ]
        assert conn.execute("SELECT COUNT(*) FROM entity_relations").fetchone()[0] == 0


@pytest.mark.anyio
async def test_cleanup_empty_sessions_removes_dependent_diagnostics(
    tmp_path,
    monkeypatch,
):
    memory_db = str(tmp_path / "memory.db")
    sessions_db = str(tmp_path / "sessions.db")
    _create_memory_db(memory_db)
    _create_sessions_db(sessions_db)
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", memory_db)
    monkeypatch.setenv("SESSIONS_DB_PATH", sessions_db)
    monkeypatch.setattr(
        quality,
        "_backup_connection",
        lambda *_args, **_kwargs: str(tmp_path / "backup.db"),
    )
    with sqlite3.connect(sessions_db) as conn:
        conn.executemany(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            [("empty", "Empty", "2026-07-01"), ("active", "Active", "2026-07-01")],
        )
        conn.execute("INSERT INTO messages VALUES (1, 'active')")
        conn.execute("INSERT INTO debug_info VALUES ('empty')")

    result = await quality._cleanup_empty_sessions(dry_run=False, confirm=True)

    assert "Eliminadas 1 sesiones" in result
    with sqlite3.connect(sessions_db) as conn:
        assert conn.execute("SELECT session_id FROM sessions").fetchall() == [
            ("active",)
        ]
        assert conn.execute("SELECT COUNT(*) FROM debug_info").fetchone()[0] == 0


@pytest.mark.anyio
async def test_rebuild_topic_relations_uses_cluster_keyword_overlap(
    tmp_path,
    monkeypatch,
):
    memory_db = str(tmp_path / "memory.db")
    sessions_db = str(tmp_path / "sessions.db")
    _create_memory_db(memory_db)
    _create_sessions_db(sessions_db)
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", memory_db)
    monkeypatch.setenv("SESSIONS_DB_PATH", sessions_db)
    monkeypatch.setattr(
        quality,
        "_backup_connection",
        lambda *_args, **_kwargs: str(tmp_path / "backup.db"),
    )
    with sqlite3.connect(memory_db) as conn:
        conn.executemany(
            "INSERT INTO topic_clusters VALUES (?, ?, 1.0)",
            [
                ("a", '[{"word":"memory"},{"word":"graph"}]'),
                ("b", '[{"word":"memory"},{"word":"graph"},{"word":"curator"}]'),
            ],
        )

    result = await quality._rebuild_topic_relations(
        dry_run=False,
        confirm=True,
    )

    assert "Reconstruidas 1 relaciones" in result
    with sqlite3.connect(memory_db) as conn:
        row = conn.execute(
            "SELECT source_id, target_id, shared_count FROM topic_relations"
        ).fetchone()
    assert row == ("a", "b", 2)


@pytest.mark.anyio
async def test_backfill_historical_tool_calls_is_idempotent(
    tmp_path,
    monkeypatch,
):
    sessions_db = str(tmp_path / "sessions.db")
    with sqlite3.connect(sessions_db) as conn:
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)"
        )
        conn.execute(
            """CREATE TABLE messages (
                id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                created_at TEXT, tool_calls TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE tool_calls (
                id INTEGER PRIMARY KEY, session_id TEXT, tool_name TEXT,
                input TEXT, status TEXT, created_at TEXT, turn INTEGER
            )"""
        )
        conn.execute(
            """INSERT INTO messages VALUES (
                1, 'old-session', 'assistant', '2026-06-15T10:00:00',
                '[{"id":"call_1","function":{"name":"read_file","arguments":"{\\"path\\":\\"a.py\\"}"}}]'
            )"""
        )
    monkeypatch.setenv("SESSIONS_DB_PATH", sessions_db)
    monkeypatch.setattr(
        quality,
        "_backup_connection",
        lambda *_args, **_kwargs: str(tmp_path / "backup.db"),
    )

    preview = await quality._backfill_historical_tool_calls(dry_run=True)
    applied = await quality._backfill_historical_tool_calls(
        dry_run=False, confirm=True
    )
    second = await quality._backfill_historical_tool_calls(
        dry_run=False, confirm=True
    )

    assert "1 llamadas históricas" in preview
    assert "Recuperadas 1 llamadas históricas" in applied
    assert "Recuperadas 0 llamadas históricas" in second
    with sqlite3.connect(sessions_db) as conn:
        assert conn.execute(
            "SELECT tool_name, status FROM tool_calls"
        ).fetchall() == [("read_file", "historical")]


@pytest.mark.anyio
async def test_prune_indirect_cooccurrence_keeps_typed_relations(
    tmp_path,
    monkeypatch,
):
    memory_db = str(tmp_path / "memory.db")
    sessions_db = str(tmp_path / "sessions.db")
    _create_memory_db(memory_db)
    _create_sessions_db(sessions_db)
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", memory_db)
    monkeypatch.setenv("SESSIONS_DB_PATH", sessions_db)
    monkeypatch.setattr(
        quality,
        "_backup_connection",
        lambda *_args, **_kwargs: str(tmp_path / "backup.db"),
    )
    with sqlite3.connect(memory_db) as conn:
        conn.executemany(
            "INSERT INTO entities VALUES (?, ?, ?, ?)",
            [
                ("kchat", "K-Chat", "proyecto", 4),
                ("sqlite", "SQLite", "tecnologia", 4),
                ("entity:concept:noise", "original", "concept", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO entity_relations VALUES (?, ?, ?, ?)",
            [
                ("kchat", "sqlite", "USA", 1.0),
                ("sqlite", "entity:concept:noise", "co_occurrence", 0.9),
            ],
        )

    preview = await quality._prune_indirect_cooccurrence(
        entity_id="K-Chat", dry_run=True
    )
    applied = await quality._prune_indirect_cooccurrence(
        entity_id="K-Chat", dry_run=False, confirm=True
    )

    assert "1 conexiones" in preview
    assert "Eliminadas 1 conexiones" in applied
    with sqlite3.connect(memory_db) as conn:
        assert conn.execute(
            "SELECT source_id, target_id, relation_type FROM entity_relations"
        ).fetchall() == [("kchat", "sqlite", "USA")]
        assert conn.execute(
            "SELECT id FROM entities ORDER BY id"
        ).fetchall() == [("kchat",), ("sqlite",)]
