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


_IDENTITY_COLUMNS = ("pipeline", "pipeline_version", "model_id", "model_version")
_PRIMARY_KEY_COLUMNS = ("source", "source_key", "item_idx", *_IDENTITY_COLUMNS)


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
                PRIMARY KEY (source, source_key, item_idx, pipeline, pipeline_version, model_id, model_version)
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_work_catalog)").fetchall()}
        for column, sql_type in [
            ("reason", "TEXT NOT NULL DEFAULT ''"),
            ("created_at", "TEXT NOT NULL DEFAULT ''"),
            ("updated_at", "TEXT NOT NULL DEFAULT ''"),
            ("metadata", "TEXT NOT NULL DEFAULT '{}'"),
            ("pipeline", f"TEXT NOT NULL DEFAULT '{defaults['pipeline']}'"),
            ("pipeline_version", f"TEXT NOT NULL DEFAULT '{defaults['pipeline_version']}'"),
            ("model_id", f"TEXT NOT NULL DEFAULT '{defaults['model_id']}'"),
            ("model_version", f"TEXT NOT NULL DEFAULT '{defaults['model_version']}'"),
            ("source_node_id", "TEXT NOT NULL DEFAULT ''"),
        ]:
            if column not in columns:
                conn.execute(f"ALTER TABLE memory_work_catalog ADD COLUMN {column} {sql_type}")
                columns.add(column)
        MemoryWorkCatalogRepository._ensure_identity_primary_key(conn)
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

    @staticmethod
    def _primary_key_columns(conn: sqlite3.Connection) -> tuple[str, ...]:
        pk_rows = [
            row
            for row in conn.execute("PRAGMA table_info(memory_work_catalog)").fetchall()
            if int(row[5] or 0) > 0
        ]
        return tuple(row[1] for row in sorted(pk_rows, key=lambda row: int(row[5])))

    @staticmethod
    def _ensure_identity_primary_key(conn: sqlite3.Connection) -> None:
        if MemoryWorkCatalogRepository._primary_key_columns(conn) == _PRIMARY_KEY_COLUMNS:
            return

        conn.execute("ALTER TABLE memory_work_catalog RENAME TO memory_work_catalog_old")
        conn.execute("""
            CREATE TABLE memory_work_catalog (
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
                PRIMARY KEY (source, source_key, item_idx, pipeline, pipeline_version, model_id, model_version)
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO memory_work_catalog (
                source, source_key, item_idx, content_hash,
                pipeline, pipeline_version, model_id, model_version,
                source_node_id, status, vec_rowid, reason,
                created_at, updated_at, metadata
            )
            SELECT
                source, source_key, item_idx, content_hash,
                COALESCE(NULLIF(pipeline, ''), 'embedding'),
                COALESCE(NULLIF(pipeline_version, ''), '1'),
                COALESCE(NULLIF(model_id, ''), 'fastembed-default'),
                COALESCE(NULLIF(model_version, ''), 'default'),
                COALESCE(source_node_id, ''),
                status, vec_rowid, reason,
                created_at, updated_at, metadata
            FROM memory_work_catalog_old
        """)
        conn.execute("DROP TABLE memory_work_catalog_old")

    def get(
        self,
        *,
        source: str,
        source_key: str,
        item_idx: int,
        pipeline: str | None = None,
        pipeline_version: str | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            if None in {pipeline, pipeline_version, model_id, model_version}:
                row = conn.execute(
                    """
                    SELECT source, source_key, item_idx, content_hash,
                           pipeline, pipeline_version, model_id, model_version,
                           source_node_id, status, vec_rowid, reason,
                           created_at, updated_at, metadata
                    FROM memory_work_catalog
                    WHERE source = ? AND source_key = ? AND item_idx = ?
                    ORDER BY updated_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (source, source_key, item_idx),
                ).fetchone()
                return dict(row) if row else None
            row = conn.execute(
                """
                SELECT source, source_key, item_idx, content_hash,
                       pipeline, pipeline_version, model_id, model_version,
                       source_node_id, status, vec_rowid, reason,
                       created_at, updated_at, metadata
                FROM memory_work_catalog
                WHERE source = ? AND source_key = ? AND item_idx = ?
                  AND pipeline = ? AND pipeline_version = ?
                  AND model_id = ? AND model_version = ?
                """,
                (source, source_key, item_idx, pipeline, pipeline_version, model_id, model_version),
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
        row = self.get(
            source=source,
            source_key=source_key,
            item_idx=item_idx,
            pipeline=pipeline,
            pipeline_version=pipeline_version,
            model_id=model_id,
            model_version=model_version,
        )
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
            # Atomic upsert: INSERT ... ON CONFLICT DO UPDATE eliminates the
            # race where two concurrent writers both UPDATE (rowcount=0) and
            # both INSERT, causing IntegrityError.
            conn.execute(
                """
                INSERT INTO memory_work_catalog (
                    source, source_key, item_idx, content_hash,
                    pipeline, pipeline_version, model_id, model_version,
                    source_node_id, status, vec_rowid, reason,
                    created_at, updated_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, source_key, item_idx, pipeline, pipeline_version, model_id, model_version)
                DO UPDATE SET
                    content_hash = ?,
                    pipeline = ?,
                    pipeline_version = ?,
                    model_id = ?,
                    model_version = ?,
                    source_node_id = ?,
                    status = ?,
                    vec_rowid = ?,
                    reason = ?,
                    updated_at = ?,
                    metadata = ?
                """,
                (
                    # VALUES for INSERT
                    source, source_key, item_idx, content_hash,
                    pipeline, pipeline_version, model_id, model_version,
                    source_node_id, status, vec_rowid, reason,
                    now, now, meta_json,
                    # SET values for ON CONFLICT DO UPDATE
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
