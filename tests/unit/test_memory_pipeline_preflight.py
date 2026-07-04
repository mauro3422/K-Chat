from __future__ import annotations

import sqlite3

from scripts.memory_audit import _content_hash
from scripts.memory_pipeline_preflight import build_pipeline_report, compare_snapshots, run_local_pipeline, run_remote_pipeline


def _init_sessions_db(path) -> str:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO sessions (session_id, name, created_at) VALUES ('s1', 'Session One', '2026-06-28T10:00:00')"
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES ('s1', 'user', ?, '2026-06-28T10:00:00')",
        ("Tell me a meaningful thing about memory pipeline audits.",),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES ('s1', 'assistant', ?, '2026-06-28T10:00:01')",
        ("Memory pipeline audits should be idempotent across local and remote nodes.",),
    )
    conn.commit()
    conn.close()
    return (
        "User: Tell me a meaningful thing about memory pipeline audits.\n"
        "Assistant: Memory pipeline audits should be idempotent across local and remote nodes."
    )


def _init_memory_db(path, exchange_text: str) -> None:
    digest = _content_hash(exchange_text)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE memory_index (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.execute(
        """
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT,
            exchange_idx INTEGER,
            text TEXT,
            hash TEXT,
            content_hash TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE memory_work_catalog (
            source TEXT,
            source_key TEXT,
            item_idx INTEGER,
            content_hash TEXT,
            status TEXT,
            vec_rowid INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
        VALUES (1, 'session', 's1', 0, ?, ?, ?, '2026-06-28T10:00:01')
        """,
        (exchange_text, digest, digest),
    )
    conn.commit()
    conn.close()


def test_memory_pipeline_preflight_runs_backfill_then_audit(tmp_path):
    sessions_db = tmp_path / "sessions.db"
    memory_db = tmp_path / "memory.db"
    exchange_text = _init_sessions_db(sessions_db)
    _init_memory_db(memory_db, exchange_text)

    result = run_local_pipeline(
        node="local-test",
        sessions_db=str(sessions_db),
        memory_db=str(memory_db),
        root=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["backfill"]["sessions_observed"] == 1
    assert result["snapshot"]["sessions"] == 1
    assert result["snapshot"]["vectors"] == 1
    assert result["snapshot"]["processing_total"] == 1
    assert result["issues"] == []


def test_memory_pipeline_report_keeps_node_differences_separate_from_failures():
    local = {
        "node": "local",
        "ok": True,
        "snapshot": {"sessions": 2, "vectors": 5, "processing_total": 3},
    }
    remote = {
        "node": "remote",
        "ok": True,
        "snapshot": {"sessions": 1, "vectors": 4, "processing_total": 3},
    }

    differences = compare_snapshots([local, remote])
    report = build_pipeline_report([local, remote])

    assert differences[0]["differences"]["sessions"] == {"local": 2, "remote": 1}
    assert differences[0]["differences"]["vectors"] == {"local": 5, "remote": 4}
    assert report["ok"] is True


class _FailingJsonRunner:
    def run_json(self, command: str, *, timeout: int):
        return {
            "node": "remote",
            "ok": False,
            "command_exit_code": 2,
            "snapshot": {"sessions": 37, "vectors": 173, "processing_total": 38},
            "issues": ["stale session vectors=2"],
        }


def test_run_remote_pipeline_preserves_failed_json_payload():
    result = run_remote_pipeline(node="remote", runner=_FailingJsonRunner())

    assert result["ok"] is False
    assert result["command_exit_code"] == 2
    assert result["snapshot"]["sessions"] == 37
    assert result["issues"] == ["stale session vectors=2"]
