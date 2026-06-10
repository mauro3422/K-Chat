import logging
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class ToolCallRepository(_BaseRepository):

    def log(self, session_id: str, tool_name: str, input_str: str, status: str, turn: int = 0) -> None:
        """Log a tool call to the database."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tool_calls (session_id, tool_name, input, status, turn, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, tool_name, input_str, status, turn, datetime.now().isoformat()))

    def delete_by_session(self, session_id: str, cursor: Any = None) -> None:
        """Delete all tool calls for a session. Pass cursor for atomic orchestration."""
        if cursor is not None:
            cursor.execute("DELETE FROM tool_calls WHERE session_id = ?", (session_id,))
        else:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tool_calls WHERE session_id = ?", (session_id,))

    def get_history(self, session_id: str, limit: int = 10) -> list[tuple[Any, ...]]:
        """Retrieve tool call history for a session."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT tool_name, input, status, created_at, turn
                FROM tool_calls
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (session_id, limit))
            return cursor.fetchall()
        except Exception:
            logger.exception("Failed to get tool history for %s", session_id)
            return []


__all__ = ["ToolCallRepository"]
