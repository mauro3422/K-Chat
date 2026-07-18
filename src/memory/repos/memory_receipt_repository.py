"""Repository for compact, session-scoped memory injection receipts."""

from __future__ import annotations

from typing import Any

from src.memory.repos.base import _BaseRepository


class MemoryReceiptRepository(_BaseRepository):
    _table_name = "memory_receipts"

    async def upsert_many(self, session_id: str, receipts: list[dict[str, Any]]) -> None:
        if not session_id or not receipts:
            return
        async with self._transaction() as conn:
            for receipt in receipts:
                await conn.execute(
                    """
                    INSERT INTO memory_receipts (
                        receipt_id, session_id, source, source_key, item_idx,
                        vec_rowid, content_hash, tag, excerpt, trigger_query
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, source, source_key, item_idx)
                    DO UPDATE SET
                        receipt_id=excluded.receipt_id,
                        vec_rowid=excluded.vec_rowid,
                        content_hash=excluded.content_hash,
                        tag=excluded.tag,
                        excerpt=excluded.excerpt,
                        trigger_query=excluded.trigger_query,
                        injection_count=memory_receipts.injection_count + 1,
                        last_injected_at=datetime('now')
                    """,
                    (
                        receipt["receipt_id"],
                        session_id,
                        receipt.get("source", ""),
                        receipt.get("source_key", ""),
                        int(receipt.get("item_idx", 0)),
                        receipt.get("vec_rowid"),
                        receipt.get("content_hash", ""),
                        receipt.get("tag", ""),
                        receipt.get("excerpt", ""),
                        receipt.get("trigger_query", ""),
                    ),
                )

    async def list_recent(
        self,
        session_id: str,
        *,
        limit: int = 16,
        exclude_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not session_id:
            return []
        excluded = exclude_ids or set()
        fetch_limit = max(1, min(int(limit) + len(excluded), 100))
        async with self._connection() as conn:
            cursor = await conn.execute(
                """
                SELECT receipt_id, session_id, source, source_key, item_idx,
                       vec_rowid, content_hash, tag, excerpt, trigger_query,
                       injection_count, injected_at, last_injected_at, last_hydrated_at
                FROM memory_receipts
                WHERE session_id=?
                ORDER BY last_injected_at DESC, receipt_id
                LIMIT ?
                """,
                (session_id, fetch_limit),
            )
            rows = [dict(row) for row in await cursor.fetchall()]
        return [row for row in rows if row["receipt_id"] not in excluded][:limit]

    async def get(self, session_id: str, receipt_id: str) -> dict[str, Any] | None:
        if not session_id or not receipt_id:
            return None
        async with self._connection() as conn:
            cursor = await conn.execute(
                """
                SELECT receipt_id, session_id, source, source_key, item_idx,
                       vec_rowid, content_hash, tag, excerpt, trigger_query,
                       injection_count, injected_at, last_injected_at, last_hydrated_at
                FROM memory_receipts
                WHERE session_id=? AND receipt_id=?
                """,
                (session_id, receipt_id),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def search(self, session_id: str, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        if not session_id or not query.strip():
            return []
        pattern = f"%{query.strip()}%"
        async with self._connection() as conn:
            cursor = await conn.execute(
                """
                SELECT receipt_id, session_id, source, source_key, item_idx,
                       vec_rowid, content_hash, tag, excerpt, trigger_query,
                       injection_count, injected_at, last_injected_at, last_hydrated_at
                FROM memory_receipts
                WHERE session_id=?
                  AND (tag LIKE ? OR excerpt LIKE ? OR trigger_query LIKE ? OR source_key LIKE ?)
                ORDER BY last_injected_at DESC
                LIMIT ?
                """,
                (session_id, pattern, pattern, pattern, pattern, max(1, min(int(limit), 20))),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def count(self, session_id: str) -> int:
        if not session_id:
            return 0
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) AS count FROM memory_receipts WHERE session_id=?",
                (session_id,),
            )
            row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def touch_hydrated(self, session_id: str, receipt_id: str) -> None:
        async with self._transaction() as conn:
            await conn.execute(
                """
                UPDATE memory_receipts
                SET last_hydrated_at=datetime('now')
                WHERE session_id=? AND receipt_id=?
                """,
                (session_id, receipt_id),
            )


__all__ = ["MemoryReceiptRepository"]
