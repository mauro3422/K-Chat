"""Vector store wrapper around sqlite-vec.

Provides insert, search (KNN), delete, and metadata filtering
on top of sqlite-vec's virtual table.
"""

from __future__ import annotations
import json
import sqlite3
import threading
import logging
from datetime import datetime
from typing import Optional

import sqlite_vec

from .models import VectorEntry, SearchResult

logger = logging.getLogger(__name__)


def compute_relevance(
    *,
    avg_tfidf: float = 0.0,
    entity_count: int = 0,
    cluster_weight: float = 0.5,
    days_old: float = 0.0,
    source: str = "session",
) -> float:
    """Compute relevance_score (0.0-1.0) from available signals."""
    tfidf_factor = avg_tfidf
    entity_factor = min(entity_count / 10.0, 1.0)
    recency_factor = max(0.0, 1.0 - days_old / 30.0)
    source_factor = 1.0 if source == "memory" else 0.7

    score = (
        tfidf_factor * 0.30
        + entity_factor * 0.20
        + cluster_weight * 0.20
        + recency_factor * 0.15
        + source_factor * 0.15
    )
    return max(0.0, min(1.0, score))


class VectorStore:
    """sqlite-vec backed vector store for embeddings."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    # --- Connection management ---

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_tables()
        return self._conn

    def _init_tables(self):
        """Ensure vector store tables exist (fallback if migration hasn't run).

        Primary table creation happens via memory_schema.py migrations.
        This is a safety net for the case where the DB exists but is
        pre-migration (e.g., freshly cloned repo).
        """
        conn = self._conn
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
                embedding float[384] distance_metric=cosine
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vec_meta (
                rowid INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                source_key TEXT NOT NULL DEFAULT '',
                exchange_idx INTEGER NOT NULL DEFAULT 0,
                text TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                hash TEXT NOT NULL DEFAULT '',
                relevance_score REAL NOT NULL DEFAULT 0.5,
                query_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT NOT NULL DEFAULT '',
                content_hash TEXT
            )
        """)
        # Safety: add columns if table existed before migrations
        for col in [
            ("hash", "TEXT DEFAULT ''"),
            ("content_hash", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE vec_meta ADD COLUMN {col[0]} {col[1]}")
            except Exception:
                logger.debug("Column %s already exists in vec_meta (safe)", col[0])

        # Create indexes if they don't exist
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        if "idx_vec_meta_source" not in existing:
            conn.execute("CREATE INDEX idx_vec_meta_source ON vec_meta (source, source_key)")
        if "idx_vec_meta_hash" not in existing:
            conn.execute("CREATE INDEX idx_vec_meta_hash ON vec_meta (hash)")
        if "idx_vec_meta_content_hash" not in existing:
            conn.execute("CREATE INDEX idx_vec_meta_content_hash ON vec_meta (content_hash)")
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

    # --- CRUD operations ---

    def insert(self, embedding: list[float], *,
               source: str = "",
               source_key: str = "",
               exchange_idx: int = 0,
               text: str = "",
               metadata: Optional[dict] = None,
               hash: str = "",
               content_hash: str = "") -> int:
        """Insert a vector and its metadata. Returns the rowid.

        Args:
            hash: Optional MD5 hash of the source text, used for deduplication.
            content_hash: Normalized MD5 hash for cross-session dedup.
        """
        with self._lock:
            conn = self._get_conn()
            now = datetime.now().isoformat(timespec="seconds")
            meta_json = json.dumps(metadata or {})

            # Insert vector into vec0
            vec_array = f"[{','.join(str(v) for v in embedding)}]"
            conn.execute(
                "INSERT INTO vec_entries(embedding) VALUES (?)",
                [vec_array]
            )
            rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Compute initial relevance score
            score = compute_relevance(source=source, days_old=0.0)

            # Insert metadata
            conn.execute(
                "INSERT INTO vec_meta(rowid, source, source_key, exchange_idx, text, metadata, created_at, hash, relevance_score, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [rowid, source, source_key, exchange_idx, text, meta_json, now, hash, round(score, 4), content_hash]
            )
            conn.commit()
            return rowid

    def search(self, query_embedding: list[float], k: int = 10,
               source_filter: Optional[str] = None,
               min_relevance: float = 0.0,
               exclude_source_key: Optional[str] = None) -> list[SearchResult]:
        """Search for the k nearest neighbors.

        Args:
            query_embedding: The query vector.
            k: Number of results (default 10, max 50).
            source_filter: Optional filter by source ('memory' or 'session').
            min_relevance: Minimum relevance_score filter (0.0 = no filter).
            exclude_source_key: If set, exclude entries with this source_key
                (e.g. current session_id to avoid self-retrieval).

        Returns:
            List of SearchResult ordered by similarity (closest first).
        """
        with self._lock:
            conn = self._get_conn()
            vec_array = f"[{','.join(str(v) for v in query_embedding)}]"
            k = min(k, 50)

            where_clauses = ["m.relevance_score >= ?"]
            params: list = [vec_array, k, min_relevance]

            if source_filter:
                where_clauses.append("m.source = ?")
                params.append(source_filter)
            if exclude_source_key:
                where_clauses.append("m.source_key != ?")
                params.append(exclude_source_key)

            where_sql = " AND ".join(where_clauses)

            rows = conn.execute(
                f"""
                SELECT v.rowid, v.distance, m.source, m.source_key,
                       m.exchange_idx, m.text, m.metadata, m.created_at
                FROM (
                    SELECT rowid, distance
                    FROM vec_entries
                    WHERE embedding MATCH ?
                    AND k = ?
                ) v
                JOIN vec_meta m ON v.rowid = m.rowid
                WHERE {where_sql}
                ORDER BY v.distance
                """,
                params
            ).fetchall()

            results = []
            for row in rows:
                entry = VectorEntry(
                    id=row[0],
                    source=row[2],
                    source_key=row[3],
                    exchange_idx=row[4],
                    text=row[5],
                    metadata=row[6],
                    created_at=row[7],
                )
                distance = row[1] if row[1] is not None else 1.0
                results.append(SearchResult(entry=entry, distance=distance, score=1.0 - distance))

            if results:
                now = datetime.now().isoformat(timespec="seconds")
                rowids = [r.entry.id for r in results]
                placeholders = ",".join("?" for _ in rowids)
                conn.execute(
                    f"UPDATE vec_meta SET query_count = query_count + 1, last_accessed = ? WHERE rowid IN ({placeholders})",
                    [now, *rowids]
                )
                conn.commit()

            return results

    def find_by_hash(self, hash: str, source: str = "") -> Optional[int]:
        """Find a vector entry by its text hash. Returns rowid or None.

        Used for deduplication: if the same text has already been embedded,
        we skip creating a duplicate embedding.
        """
        with self._lock:
            conn = self._get_conn()
            if source:
                row = conn.execute(
                    "SELECT rowid FROM vec_meta WHERE hash = ? AND source = ? LIMIT 1",
                    [hash, source]
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT rowid FROM vec_meta WHERE hash = ? LIMIT 1",
                    [hash]
                ).fetchone()
            return row[0] if row else None

    def delete(self, rowid: int) -> bool:
        """Delete a vector entry by rowid."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM vec_entries WHERE rowid = ?", [rowid])
            conn.execute("DELETE FROM vec_meta WHERE rowid = ?", [rowid])
            conn.commit()
        return cursor.rowcount > 0

    def delete_by_source(self, source_key: str, source: str = "") -> int:
        """Delete entries for a source key, optionally scoped by source type.

        Scoping matters because memory keys and session IDs share the same
        ``source_key`` column. Callers that know the domain should pass
        ``source='memory'`` or ``source='session'``.
        """
        with self._lock:
            conn = self._get_conn()
            where_sql = "source_key = ?"
            params: list = [source_key]
            if source:
                where_sql += " AND source = ?"
                params.append(source)
            rows = conn.execute(f"SELECT rowid FROM vec_meta WHERE {where_sql}", params).fetchall()
            for (rowid,) in rows:
                conn.execute("DELETE FROM vec_entries WHERE rowid = ?", [rowid])
            deleted = conn.execute(f"DELETE FROM vec_meta WHERE {where_sql}", params).rowcount
            conn.commit()
            return deleted

    def count(self, source: Optional[str] = None) -> int:
        """Count total entries, optionally filtered by source."""
        with self._lock:
            conn = self._get_conn()
            if source:
                return conn.execute(
                    "SELECT COUNT(*) FROM vec_meta WHERE source = ?", [source]
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM vec_meta").fetchone()[0]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()
