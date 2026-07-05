from __future__ import annotations

import sqlite3
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.memory.curator import curate
from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository
from src.memory.synthesis.daily import generate_daily_synthesis


@pytest.mark.anyio
async def test_curate_all_passes_sessions_db_to_daily_synthesis(tmp_path):
    save_memory = AsyncMock(return_value="[OK] saved")
    llm_call = AsyncMock(return_value="NO_NEW_INFO")
    synth = AsyncMock(return_value="memory/synthesis/2026/06/27.md")

    with (
        patch("src.memory.curator.curate._get_sessions_db_path", return_value="sessions.db"),
        patch("src.memory.curator.curate._get_memory_db_path", return_value="memory.db"),
        patch("src.memory.vectorize_sessions.vectorize_all_sessions", new=AsyncMock(return_value={})),
        patch("src.memory.repos.get_repos", return_value=SimpleNamespace()),
        patch("src.memory.curator.curate.curate_clusters", new=AsyncMock(return_value=[])),
        patch("src.memory.curator.curate.curate_sessions", new=AsyncMock(return_value=[])),
        patch("src.memory.synthesis.daily.generate_daily_synthesis", new=synth),
        patch("src.memory.curator.curate._get_processing_catalog", return_value=None),
    ):
        result = await curate.curate_all(
            dry=False,
            save_memory_fn=save_memory,
            llm_call_fn=llm_call,
            run_gardener=False,
            run_tracer=False,
            artifact_root=tmp_path,
        )

    synth.assert_awaited_once_with(db_path="sessions.db")
    assert result["synthesis_path"] == "memory/synthesis/2026/06/27.md"
    assert result["report_path"]
    assert os.path.exists(result["report_path"])
    save_memory.assert_not_awaited()


@pytest.mark.anyio
async def test_curate_sessions_skips_unchanged_cataloged_session(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"

    conn = sqlite3.connect(sessions_db)
    conn.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
    conn.execute(
        "INSERT INTO sessions (session_id, name, created_at) VALUES (?, ?, ?)",
        ("s1", "Test", datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT,
            exchange_idx INTEGER,
            text TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO vec_meta (source, source_key, exchange_idx, text)
        VALUES ('session', 's1', 1, ?)
        """,
        ("Mauro quiere evitar duplicar trabajo semantico en las curaciones.",),
    )
    conn.commit()
    conn.close()

    llm_call = AsyncMock(return_value="NO_NEW_INFO")

    with (
        patch("src.memory.curator.curate._get_sessions_db_path", return_value=str(sessions_db)),
        patch("src.memory.curator.curate._get_memory_db_path", return_value=str(memory_db)),
        patch("src.memory.curator.curate._get_memory_context", return_value=""),
    ):
        first = await curate.curate_sessions(days=1, dry=False, llm_call_fn=llm_call)
        second = await curate.curate_sessions(days=1, dry=False, llm_call_fn=llm_call)

    assert first == []
    assert second == []
    assert llm_call.await_count == 1


@pytest.mark.anyio
async def test_curate_clusters_skips_unchanged_cataloged_cluster(tmp_path):
    memory_db = tmp_path / "memory.db"
    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        CREATE TABLE topic_clusters (
            cluster_id TEXT PRIMARY KEY,
            label TEXT,
            keywords TEXT,
            exchange_count INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE exchange_clusters (
            cluster_id TEXT,
            exchange_rowid INTEGER,
            similarity REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT,
            exchange_idx INTEGER,
            text TEXT,
            metadata TEXT
        )
        """
    )
    conn.execute("INSERT INTO topic_clusters VALUES ('c1', 'memory catalog', '[]', 2)")
    conn.execute("INSERT INTO exchange_clusters VALUES ('c1', 1, 0.9)")
    conn.execute(
        "INSERT INTO vec_meta VALUES (1, 'session', 's1', 0, ?, '{}')",
        ("Mauro wants the memory curator to avoid repeated LLM work across unchanged clusters.",),
    )
    conn.commit()
    conn.close()

    llm_call = AsyncMock(return_value="NO_NEW_INFO")

    with (
        patch("src.memory.curator.curate._get_memory_db_path", return_value=str(memory_db)),
        patch("src.memory.curator.curate._get_memory_context", return_value=""),
    ):
        first = await curate.curate_clusters(dry=False, llm_call_fn=llm_call)
        second = await curate.curate_clusters(dry=False, llm_call_fn=llm_call)

    catalog = MemoryProcessingCatalogRepository(str(memory_db))
    row = catalog.get(source="cluster", source_key="c1", item_idx=-1, stage="curated")
    assert first == []
    assert second == []
    assert llm_call.await_count == 1
    assert row is not None
    assert row["status"] == "processed"
    assert row["processor"] == "curate_clusters"


@pytest.mark.anyio
async def test_curate_all_registers_curator_run_in_processing_catalog(tmp_path):
    memory_db = tmp_path / "memory.db"
    save_memory = AsyncMock(return_value="[OK] saved")
    llm_call = AsyncMock(return_value="NO_NEW_INFO")
    synth = AsyncMock(return_value="memory/synthesis/2026/07/01.md")

    with (
        patch("src.memory.curator.curate._get_sessions_db_path", return_value=str(tmp_path / "sessions.db")),
        patch("src.memory.curator.curate._get_memory_db_path", return_value=str(memory_db)),
        patch("src.memory.vectorize_sessions.vectorize_all_sessions", new=AsyncMock(return_value={})),
        patch("src.memory.repos.get_repos", return_value=SimpleNamespace()),
        patch("src.memory.curator.curate.curate_clusters", new=AsyncMock(return_value=[])),
        patch("src.memory.curator.curate.curate_sessions", new=AsyncMock(return_value=[])),
        patch("src.memory.synthesis.daily.generate_daily_synthesis", new=synth),
    ):
        await curate.curate_all(
            dry=False,
            save_memory_fn=save_memory,
            llm_call_fn=llm_call,
            run_gardener=False,
            run_tracer=False,
            artifact_root=tmp_path,
        )

    catalog = MemoryProcessingCatalogRepository(str(memory_db))
    row = catalog.get(source="curator", source_key=datetime.now().strftime("%Y-%m-%d"), item_idx=-1, stage="run")
    assert row is not None
    assert row["status"] == "processed"
    assert row["processor"] == "curate_all"
    save_memory.assert_not_awaited()


@pytest.mark.anyio
async def test_daily_synthesis_registers_generated_report_in_processing_catalog(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    today = datetime.now().date().isoformat()

    conn = sqlite3.connect(sessions_db)
    conn.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
    conn.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created_at TEXT)"
    )
    conn.execute("INSERT INTO sessions VALUES ('s1', 'Daily Test', ?)", (f"{today}T10:00:00",))
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES ('s1', 'user', 'hola', ?)",
        (f"{today}T10:00:00",),
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(memory_db)
    conn.execute(
        """
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute("CREATE TABLE memory_index (key TEXT, value TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE entities (id TEXT, name TEXT, entity_type TEXT, mention_count INTEGER, first_seen TEXT)")
    conn.execute(
        "CREATE TABLE topic_clusters (cluster_id TEXT, label TEXT, keywords TEXT, session_count INTEGER, exchange_count INTEGER, first_seen TEXT, weight REAL)"
    )
    conn.execute("CREATE TABLE exchange_clusters (cluster_id TEXT, exchange_rowid INTEGER)")
    conn.commit()
    conn.close()

    with patch("src.memory.synthesis.daily.resolve_memory_db_path", return_value=str(memory_db)):
        report_path = await generate_daily_synthesis(
            db_path=str(sessions_db),
            target_date=datetime.now().date(),
        )

    catalog = MemoryProcessingCatalogRepository(str(memory_db))
    row = catalog.get(source="daily_synthesis", source_key=today, item_idx=-1, stage="generated")
    assert os.path.exists(report_path)
    assert row is not None
    assert row["status"] == "processed"
    assert row["processor"] == "generate_daily_synthesis"
