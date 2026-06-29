"""Repository for memory work catalog rows.

The catalog tracks logical processing units independently from the physical
embedding rows in vec_meta. This lets deduplicated content still mark every
source item as processed.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path


def _catalog_identity_defaults() -> dict[str, str]:
    return {
        "pipeline": "embedding",
        "pipeline_version": "1",
        "model_id": "fastembed-default",
        "model_version": "default",
        "source_node_id": "",
    }


class MemoryWorkCatalogRepository:
    """SQLite repository for memory_work_catalog."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or resolve_memory_db_path()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        self.ensure_schema(conn)
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        defaults = _catalog_identity_defaults()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_work_catalog (
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                item_idx INTEGER NOT NULL,
                content_hash TEXT NOT NULL DEFAULT '',
                pipeline TEXT NOT NULL DEFAULT 'embedding',
                pipeline_version TEXT NOT NULL DEFAULT '1',
                model_id TEXT NOT NULL DEFAULT 'fastembed-default',
                model_version TEXT NOT NULL DEFAULT 'default',
                source_node_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                vec_rowid INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                metadata TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (source, source_key, item_idx)
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_work_catalog)").fetchall()}
        for column, sql_type in [
            ("pipeline", f"TEXT NOT NULL DEFAULT '{defaults['pipeline']}'"),
            ("pipeline_version", f"TEXT NOT NULL DEFAULT '{defaults['pipeline_version']}'"),
            ("model_id", f"TEXT NOT NULL DEFAULT '{defaults['model_id']}'"),
            ("model_version", f"TEXT NOT NULL DEFAULT '{defaults['model_version']}'"),
            ("source_node_id", "TEXT NOT NULL DEFAULT ''"),
        ]:
            if column not in columns:
                conn.execute(f"ALTER TABLE memory_work_catalog ADD COLUMN {column} {sql_type}")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_work_catalog_status
            ON memory_work_catalog (status, updated_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_work_catalog_hash
            ON memory_work_catalog (content_hash)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_work_catalog_vec
            ON memory_work_catalog (vec_rowid)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_work_catalog_identity
            ON memory_work_catalog (source, source_key, item_idx, pipeline, pipeline_version, model_id, model_version)
        """)
        conn.commit()

    def get(self, *, source: str, source_key: str, item_idx: int) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT source, source_key, item_idx, content_hash,
                       pipeline, pipeline_version, model_id, model_version,
                       source_node_id, status, vec_rowid, reason,
                       created_at, updated_at, metadata
                FROM memory_work_catalog
                WHERE source = ? AND source_key = ? AND item_idx = ?
                """,
                (source, source_key, item_idx),
            ).fetchone()
            return dict(row) if row else None

    def is_processed(
        self,
        *,
        source: str,
        source_key: str,
        item_idx: int,
        content_hash: str,
        pipeline: str = "embedding",
        pipeline_version: str = "1",
        model_id: str = "fastembed-default",
        model_version: str = "default",
    ) -> bool:
        row = self.get(source=source, source_key=source_key, item_idx=item_idx)
        return bool(
            row
            and row["content_hash"] == content_hash
            and row["pipeline"] == pipeline
            and row["pipeline_version"] == pipeline_version
            and row["model_id"] == model_id
            and row["model_version"] == model_version
            and row["status"] in {"embedded", "deduped", "noise"}
        )

    def mark(
        self,
        *,
        source: str,
        source_key: str,
        item_idx: int,
        content_hash: str,
        status: str,
        vec_rowid: int | None = None,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
        pipeline: str = "embedding",
        pipeline_version: str = "1",
        model_id: str = "fastembed-default",
        model_version: str = "default",
        source_node_id: str = "",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        meta_json = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO memory_work_catalog (
                    source, source_key, item_idx, content_hash,
                    pipeline, pipeline_version, model_id, model_version,
                    source_node_id, status, vec_rowid, reason,
                    created_at, updated_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_key, item_idx) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    pipeline = excluded.pipeline,
                    pipeline_version = excluded.pipeline_version,
                    model_id = excluded.model_id,
                    model_version = excluded.model_version,
                    source_node_id = excluded.source_node_id,
                    status = excluded.status,
                    vec_rowid = excluded.vec_rowid,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
                """,
                (
                    source,
                    source_key,
                    item_idx,
                    content_hash,
                    pipeline,
                    pipeline_version,
                    model_id,
                    model_version,
                    source_node_id,
                    status,
                    vec_rowid,
                    reason,
                    now,
                    now,
                    meta_json,
                ),
            )
            conn.commit()

    def max_processed_idx(self, *, source: str, source_key: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(item_idx), -1)
                FROM memory_work_catalog
                WHERE source = ? AND source_key = ?
                  AND status IN ('embedded', 'deduped', 'noise')
                """,
                (source, source_key),
            ).fetchone()
            return int(row[0]) if row else -1
