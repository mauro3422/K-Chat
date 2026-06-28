"""Repository for memory work catalog rows.

The catalog tracks logical processing units independently from the physical
embedding rows in vec_meta. This lets deduplicated content still mark every
source item as processed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path


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

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_work_catalog (
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                item_idx INTEGER NOT NULL,
                content_hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                vec_rowid INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                metadata TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (source, source_key, item_idx)
            )
        """)
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
        conn.commit()

    def get(self, *, source: str, source_key: str, item_idx: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT source, source_key, item_idx, content_hash, status,
                       vec_rowid, reason, created_at, updated_at, metadata
                FROM memory_work_catalog
                WHERE source = ? AND source_key = ? AND item_idx = ?
                """,
                (source, source_key, item_idx),
            ).fetchone()
            return dict(row) if row else None

    def is_processed(self, *, source: str, source_key: str, item_idx: int, content_hash: str) -> bool:
        row = self.get(source=source, source_key=source_key, item_idx=item_idx)
        return bool(row and row["content_hash"] == content_hash and row["status"] in {"embedded", "deduped", "noise"})

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
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        meta_json = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_work_catalog (
                    source, source_key, item_idx, content_hash, status,
                    vec_rowid, reason, created_at, updated_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_key, item_idx) DO UPDATE SET
                    content_hash = excluded.content_hash,
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
        with self._connect() as conn:
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
