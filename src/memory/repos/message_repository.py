import logging
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository
from src.memory.types import MessageRecord

logger = logging.getLogger(__name__)


class MessageRepository(_BaseRepository):
    _table_name = "messages"

    async def save(
        self,
        session_id: str,
        role: str,
        content: str | None,
        model: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: str | None = None,
        reasoning: str = "",
        phases: str = "[]",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Save a message row to the database."""
        async with self._transaction() as conn:
            await conn.execute('''
                INSERT INTO messages (session_id, role, content, model, reasoning, phases, prompt_tokens, completion_tokens, total_tokens, tool_calls, tool_call_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                role,
                content if content is not None else "",
                model,
                reasoning,
                phases,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                tool_calls,
                tool_call_id,
                datetime.now().isoformat()
            ))

    async def save_record(self, record: MessageRecord) -> None:
        """Save a MessageRecord dataclass to the database."""
        await self.save(
            session_id=record.session_id,
            role=record.role,
            content=record.content,
            model=record.model,
            tool_call_id=record.tool_call_id,
            tool_calls=record.tool_calls,
            reasoning=record.reasoning,
            phases=record.phases,
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            total_tokens=record.total_tokens,
        )

    async def get_session_messages(self, session_id: str, limit: int = 500) -> list[tuple[Any, ...]]:
        """Retrieve messages for a session, ordered by creation time."""
        try:
            async with self._connection() as conn:
                cursor = await conn.execute('''
                    SELECT role, content, model, created_at, reasoning, phases, tool_calls, tool_call_id, id
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id ASC
                    LIMIT ?
                ''', (session_id, limit))
                return await cursor.fetchall()
        except Exception:
            logger.exception("Failed to get session messages for %s", session_id)
            return []

    async def get_session_exchange_window(
        self,
        session_id: str,
        item_idx: int,
        window: int = 1,
    ) -> list[tuple[Any, ...]]:
        """Return an indexed exchange and nearby exchanges without a session-wide limit."""

        anchor = max(0, int(item_idx))
        radius = max(0, min(int(window), 4))
        try:
            async with self._connection() as conn:
                cursor = await conn.execute(
                    """
                    WITH indexed AS (
                        SELECT role, content, id,
                               SUM(CASE WHEN role='user' THEN 1 ELSE 0 END)
                                   OVER (ORDER BY id) - 1 AS exchange_idx
                        FROM messages
                        WHERE session_id=?
                    )
                    SELECT role, content, exchange_idx
                    FROM indexed
                    WHERE exchange_idx BETWEEN ? AND ?
                    ORDER BY id ASC
                    """,
                    (session_id, max(0, anchor - radius), anchor + radius),
                )
                return await cursor.fetchall()
        except Exception:
            logger.exception(
                "Failed to get exchange window %s for session %s",
                anchor,
                session_id,
            )
            return []

    async def delete_session_messages(self, session_id: str) -> int:
        """Delete ALL messages for a session. Keeps the session itself."""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "DELETE FROM messages WHERE session_id = ?",
                    (session_id,)
                )
                deleted = cursor.rowcount
                if deleted:
                    logger.info("Deleted %d messages for session %s", deleted, session_id)
                return deleted
        except Exception as e:
            logger.warning("Failed to delete messages for session %s: %s", session_id, e)
            return 0

    async def delete_message(self, message_id: int) -> bool:
        """Delete a single message by its autoincrement ID."""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "DELETE FROM messages WHERE id = ?",
                    (message_id,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception("Failed to delete message with id %s: %s", message_id, e)
            return False

    async def delete_empty_assistant(self, session_id: str) -> None:
        """Delete assistant messages with empty content (left by tool loop resets).

        Only deletes messages that have NO tool_calls — otherwise it would
        orphan tool responses that depend on the assistant's tool_call_ids.
        """
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "DELETE FROM messages WHERE session_id = ? AND role = 'assistant'"
                    " AND (content IS NULL OR content = '')"
                    " AND (tool_calls IS NULL OR tool_calls = '' OR tool_calls = '[]')",
                    (session_id,)
                )
                deleted = cursor.rowcount
                if deleted:
                    logger.info("Deleted %d empty assistant messages for %s", deleted, session_id)
        except Exception as e:
            logger.warning("Failed to delete empty assistant messages: %s", e)


__all__ = ["MessageRecord", "MessageRepository"]
