"""Repository for semantic memory processing catalog rows.

The embedding work catalog answers "was this source item vectorized?".
This catalog answers "did this semantic stage already process this exact
content?", so LLM-heavy synthesis/curation/tracing can be skipped safely.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path


class MemoryProcessingCatalogRepository:
    """SQLite repository for memory_processing_catalog."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or resolve_memory_db_path()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        self.ensure_schema(conn)
        return conn

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_processing_catalog (
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                item_idx INTEGER NOT NULL,
                stage TEXT NOT NULL,
                content_hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                processor TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                metadata TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (source, source_key, item_idx, stage)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_processing_catalog_stage_status
            ON memory_processing_catalog (stage, status, updated_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_processing_catalog_hash
            ON memory_processing_catalog (content_hash)
        """)
        conn.commit()

    def get(
        self,
        *,
        source: str,
        source_key: str,
        item_idx: int,
        stage: str,
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT source, source_key, item_idx, stage, content_hash,
                       status, processor, reason, created_at, updated_at,
                       metadata
                FROM memory_processing_catalog
                WHERE source = ? AND source_key = ? AND item_idx = ? AND stage = ?
                """,
                (source, source_key, item_idx, stage),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def is_processed(
        self,
        *,
        source: str,
        source_key: str,
        item_idx: int,
        stage: str,
        content_hash: str,
    ) -> bool:
        row = self.get(source=source, source_key=source_key, item_idx=item_idx, stage=stage)
        return bool(
            row
            and row["content_hash"] == content_hash
            and row["status"] in {"processed", "skipped"}
        )

    def mark(
        self,
        *,
        source: str,
        source_key: str,
        item_idx: int,
        stage: str,
        content_hash: str,
        status: str = "processed",
        processor: str = "",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        meta_json = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO memory_processing_catalog (
                    source, source_key, item_idx, stage, content_hash, status,
                    processor, reason, created_at, updated_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_key, item_idx, stage) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    processor = excluded.processor,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
                """,
                (
                    source,
                    source_key,
                    item_idx,
                    stage,
                    content_hash,
                    status,
                    processor,
                    reason,
                    now,
                    now,
                    meta_json,
                ),
            )
            conn.commit()
        finally:
            conn.close()
