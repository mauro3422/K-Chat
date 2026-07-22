"""Replaceable checkpoints for interrupted assistant turns."""

from __future__ import annotations

from typing import Any
import sqlite3

from src.memory.repos.base import _BaseRepository


class StreamCheckpointRepository(_BaseRepository):
    _table_name = "stream_checkpoints"

    async def save(
        self,
        session_id: str,
        *,
        original_message: str,
        model: str,
        history_json: str,
        phases_json: str,
        partial_content: str = "",
        partial_reasoning: str = "",
        status: str = "open",
        checkpoint_kind: str = "",
        error_type: str = "",
        error_message: str = "",
        retry_count: int = 0,
    ) -> None:
        if not session_id:
            return
        async with self._transaction() as conn:
            await conn.execute(
                """
                INSERT INTO stream_checkpoints (
                    session_id, original_message, model, history_json, phases_json,
                    partial_content, partial_reasoning, status, checkpoint_kind,
                    error_type, error_message, retry_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    original_message=excluded.original_message,
                    model=excluded.model,
                    history_json=excluded.history_json,
                    phases_json=excluded.phases_json,
                    partial_content=excluded.partial_content,
                    partial_reasoning=excluded.partial_reasoning,
                    status=excluded.status,
                    checkpoint_kind=excluded.checkpoint_kind,
                    error_type=excluded.error_type,
                    error_message=excluded.error_message,
                    retry_count=excluded.retry_count,
                    updated_at=datetime('now')
                """,
                (
                    session_id,
                    original_message,
                    model,
                    history_json,
                    phases_json,
                    partial_content,
                    partial_reasoning,
                    status,
                    checkpoint_kind,
                    error_type,
                    error_message,
                    max(0, int(retry_count)),
                ),
            )

    async def get(self, session_id: str) -> dict[str, Any] | None:
        if not session_id:
            return None
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM stream_checkpoints WHERE session_id=?",
                (session_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def clear(self, session_id: str) -> None:
        await self.delete_by_session(session_id)

    async def delete_by_session(
        self,
        session_id: str,
        cursor: Any = None,
    ) -> None:
        try:
            await super().delete_by_session(session_id, cursor)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise


__all__ = ["StreamCheckpointRepository"]
