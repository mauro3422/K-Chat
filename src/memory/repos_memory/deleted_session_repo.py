"""Repository for deleted_sessions.db — snapshots of deleted sessions.

Stores a summary + embedding of each deleted session so semantic
search can still detect "ghost" memories even after the session is gone.
"""

from __future__ import annotations
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Generator

import sqlite_vec

from src.memory.deleted_sessions_db import (
    init_deleted_sessions_db,
    resolve_deleted_db_path,
)

logger = logging.getLogger(__name__)


# ── Data model ─────────────────────────────────────────────────────────────

@dataclass
class DeletedSessionEntry:
    """A snapshot of a deleted session."""
    session_id: str
    name: str = ""
    message_count: int = 0
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    deleted_at: str = ""
    embedding: list[float] = field(default_factory=list)

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id[:12],
            "name": self.name or "(sin título)",
            "message_count": self.message_count,
            "summary": self.summary[:200],
            "topics": self.topics,
            "deleted_at": self.deleted_at,
        }


# ── Repository ─────────────────────────────────────────────────────────────

class DeletedSessionRepository:
    """Persistence for deleted session snapshots.

    Uses a dedicated connection to ``deleted_sessions.db`` (separate from
    both sessions.db and memory.db). Backed by sqlite-vec for semantic search.

    Each method opens its own connection (context-managed) to ensure
    connections are never leaked.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or resolve_deleted_db_path()
        self._init()

    # ── Internal helpers ───────────────────────────────────────────────

    def _init(self) -> None:
        """Ensure the DB is initialized (idempotent)."""
        try:
            init_deleted_sessions_db()
        except Exception:
            logger.exception("Deleted sessions DB init failed (will retry on first use)")

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        except Exception:
            logger.warning("sqlite-vec not available for deleted_sessions.db")
        try:
            yield conn
        finally:
            conn.close()

    # ── CRUD ───────────────────────────────────────────────────────────

    def save(self, entry: DeletedSessionEntry) -> None:
        """Save a deleted session snapshot to the DB.

        Generates an embedding from the summary for semantic search.
        """
        with self._get_conn() as conn:
            now = entry.deleted_at or datetime.now().isoformat(timespec="seconds")
            topics_json = json.dumps(entry.topics)

            conn.execute(
                """INSERT OR REPLACE INTO deleted_sessions
                   (session_id, name, message_count, summary, topics, deleted_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (entry.session_id, entry.name, entry.message_count,
                 entry.summary, topics_json, now),
            )

            if entry.embedding and len(entry.embedding) > 0:
                self._save_embedding(conn, entry.session_id, entry.summary,
                                     entry.embedding, now)

            conn.commit()
            logger.info("Saved deleted session %s (%d msgs, %d topics, %d-dim embedding)",
                         entry.session_id[:12], entry.message_count,
                         len(entry.topics), len(entry.embedding))

    def _save_embedding(self, conn: sqlite3.Connection,
                        session_id: str, text: str,
                        embedding: list[float], now: str) -> None:
        """Insert a vector entry for the deleted session."""
        vec_array = f"[{','.join(str(v) for v in embedding)}]"
        metadata = json.dumps({
            "source": "deleted_session",
            "session_id": session_id,
        })

        old_rows = conn.execute(
            "SELECT rowid FROM vec_meta WHERE source_key = ?", (session_id,)
        ).fetchall()
        for (old_rowid,) in old_rows:
            conn.execute("DELETE FROM vec_entries WHERE rowid = ?", (old_rowid,))
        conn.execute("DELETE FROM vec_meta WHERE source_key = ?", (session_id,))

        conn.execute(
            "INSERT INTO vec_entries(embedding) VALUES (?)",
            [vec_array],
        )
        rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO vec_meta(rowid, source, source_key, text, metadata, created_at) "
            "VALUES (?, 'deleted_session', ?, ?, ?, ?)",
            [rowid, session_id, text[:500], metadata, now],
        )

    def get(self, session_id: str) -> DeletedSessionEntry | None:
        """Retrieve a specific deleted session by its original session_id."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT session_id, name, message_count, summary, topics, deleted_at "
                "FROM deleted_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return DeletedSessionEntry(
                session_id=row["session_id"],
                name=row["name"] or "",
                message_count=row["message_count"],
                summary=row["summary"],
                topics=json.loads(row["topics"]) if row["topics"] else [],
                deleted_at=row["deleted_at"],
            )

    def search_by_text(self, query: str, limit: int = 5) -> list[DeletedSessionEntry]:
        """Simple text search on deleted sessions (LIKE match on summary/name)."""
        with self._get_conn() as conn:
            pattern = f"%{query}%"
            rows = conn.execute(
                "SELECT session_id, name, message_count, summary, topics, deleted_at "
                "FROM deleted_sessions WHERE summary LIKE ? OR name LIKE ? "
                "ORDER BY deleted_at DESC LIMIT ?",
                (pattern, pattern, limit),
            ).fetchall()
            return [
                DeletedSessionEntry(
                    session_id=r["session_id"],
                    name=r["name"] or "",
                    message_count=r["message_count"],
                    summary=r["summary"],
                    topics=json.loads(r["topics"]) if r["topics"] else [],
                    deleted_at=r["deleted_at"],
                )
                for r in rows
            ]

    def search_by_embedding(self, query_embedding: list[float],
                            k: int = 5) -> list[tuple[DeletedSessionEntry, float]]:
        """Semantic search on deleted sessions using the embedding.

        Returns a list of (entry, similarity_score) tuples, ordered by
        relevance (highest score first).
        """
        with self._get_conn() as conn:
            vec_array = f"[{','.join(str(v) for v in query_embedding)}]"
            k = min(k, 20)

            try:
                rows = conn.execute(
                    """
                    SELECT v.rowid, v.distance, m.source_key, m.text
                    FROM (
                        SELECT rowid, distance
                        FROM vec_entries
                        WHERE embedding MATCH ?
                        AND k = ?
                    ) v
                    JOIN vec_meta m ON v.rowid = m.rowid
                    WHERE m.source = 'deleted_session'
                    ORDER BY v.distance
                    """,
                    [vec_array, k],
                ).fetchall()
            except Exception:
                logger.warning("Vector search failed (sqlite-vec not loaded?)")
                return []

            results: list[tuple[DeletedSessionEntry, float]] = []
            for row in rows:
                distance = row[1] if row[1] is not None else 1.0
                score = 1.0 - distance
                if score < 0.1:
                    continue
                source_key = row[2]
                entry = self.get(source_key)
                if entry:
                    results.append((entry, score))

            return results

    def count(self) -> int:
        """Return total number of deleted session snapshots."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM deleted_sessions").fetchone()
            return row["cnt"] if row else 0

    def list_recent(self, limit: int = 10) -> list[DeletedSessionEntry]:
        """List most recently deleted sessions."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT session_id, name, message_count, summary, topics, deleted_at "
                "FROM deleted_sessions ORDER BY deleted_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                DeletedSessionEntry(
                    session_id=r["session_id"],
                    name=r["name"] or "",
                    message_count=r["message_count"],
                    summary=r["summary"],
                    topics=json.loads(r["topics"]) if r["topics"] else [],
                    deleted_at=r["deleted_at"],
                )
                for r in rows
            ]

    # ── Cleanup ────────────────────────────────────────────────────────

    def purge_older_than(self, days: int) -> int:
        """Delete entries older than N days. Returns count removed."""
        with self._get_conn() as conn:
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            old = conn.execute(
                "SELECT session_id FROM deleted_sessions WHERE deleted_at < ?",
                (cutoff,),
            ).fetchall()

            count = len(old)
            for (sid,) in old:
                old_vec = conn.execute(
                    "SELECT rowid FROM vec_meta WHERE source_key = ?", (sid,)
                ).fetchall()
                for (rowid,) in old_vec:
                    conn.execute("DELETE FROM vec_entries WHERE rowid = ?", (rowid,))
                conn.execute("DELETE FROM vec_meta WHERE source_key = ?", (sid,))
                conn.execute("DELETE FROM deleted_sessions WHERE session_id = ?", (sid,))

            conn.commit()
            if count:
                logger.info("Purged %d deleted sessions older than %d days", count, days)
            return count


__all__ = [
    "DeletedSessionEntry",
    "DeletedSessionRepository",
]
