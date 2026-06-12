import logging
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository
from src.memory.repos.debug_repository import DebugRepository
from src.memory.repos.message_repository import MessageRepository
from src.memory.repos.saved_widget_repository import SavedWidgetRepository
from src.memory.repos.tool_call_repository import ToolCallRepository
from src.memory.repos.widget_state_repository import WidgetStateRepository

logger = logging.getLogger(__name__)


class SessionRepository(_BaseRepository):

    def ensure(self, session_id: str) -> None:
        """Create a session row if it does not exist."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO sessions (session_id, name, created_at) VALUES (?, '', ?)",
                    (session_id, datetime.now().isoformat())
                )

    def rename(self, session_id: str, name: str) -> None:
        """Rename a session."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE sessions SET name = ? WHERE session_id = ?", (name, session_id))

    def delete(self, session_id: str) -> None:
        """Delete a session and all its associated data."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            for repo_cls in [MessageRepository, ToolCallRepository, DebugRepository, WidgetStateRepository, SavedWidgetRepository]:
                repo_cls(self._conn).delete_by_session(session_id, cursor)
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_all(self, limit: int = 50) -> list[tuple[Any, ...]]:
        """Return all sessions with summary data."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT m.session_id,
                       MIN(m.created_at),
                       MAX(m.created_at),
                       COUNT(*),
                       SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END),
                       COALESCE(s.name, '')
                FROM messages m
                LEFT JOIN sessions s ON m.session_id = s.session_id
                GROUP BY m.session_id
                ORDER BY MAX(m.created_at) DESC
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
        except Exception:
            logger.exception("Failed to get all sessions")
            return []

    def check_should_rename(self, session_id: str) -> bool:
        """Check if the session should be auto-renamed (single user message, no name set)."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row and (row[0] == '' or row[0] is None):
                cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,))
                count = cursor.fetchone()[0]
                return count == 1
            return False
        except Exception:
            logger.exception("Failed to check should_rename for %s", session_id)
            return False


__all__ = ["SessionRepository"]
