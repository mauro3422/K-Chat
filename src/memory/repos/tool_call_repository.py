import logging
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class ToolCallRepository(_BaseRepository):
    _table_name = "tool_calls"

    async def log(self, session_id: str, tool_name: str, input_str: str, status: str, turn: int = 0) -> None:
        """Log a tool call to the database."""
        async with self._transaction() as conn:
            await conn.execute('''
                INSERT INTO tool_calls (session_id, tool_name, input, status, turn, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, tool_name, input_str, status, turn, datetime.now().isoformat()))

    async def record_execution(
        self,
        session_id: str,
        tool_name: str,
        input_str: str,
        status: str,
        tool_result: str,
        turn: int = 0,
        tool_call_id: str | None = None,
    ) -> None:
        """Persist both the tool call and its resulting tool message in one transaction."""
        async with self._transaction() as conn:
            created_at = datetime.now().isoformat()
            await conn.execute('''
                INSERT INTO tool_calls (session_id, tool_name, input, status, turn, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, tool_name, input_str, status, turn, created_at))
            await conn.execute('''
                INSERT INTO messages (session_id, role, content, model, tool_call_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, "tool", tool_result, None, tool_call_id, created_at))

    async def get_history(self, session_id: str, limit: int = 10) -> list[tuple[Any, ...]]:
        """Retrieve tool call history for a session."""
        try:
            async with self._connection() as conn:
                cursor = await conn.execute('''
                    SELECT tool_name, input, status, created_at, turn
                    FROM tool_calls
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (session_id, limit))
                return await cursor.fetchall()
        except Exception:
            logger.exception("Failed to get tool history for %s", session_id)
            return []


__all__ = ["ToolCallRepository"]
