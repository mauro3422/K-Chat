import logging
from datetime import datetime
from typing import Any, TYPE_CHECKING

from src.memory.repos.base import _BaseRepository

if TYPE_CHECKING:
    from src.memory.repos import Repositories

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

    def delete(self, session_id: str, cursor: Any = None) -> None:
        """Delete the session row itself."""
        if cursor is not None:
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        else:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def delete_cascade(self, session_id: str, repos: "Repositories") -> None:
        """Delete a session and all related rows in one transaction."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM widget_versions WHERE session_id = ?", (session_id,))
            for repo in (
                repos.messages,
                repos.tool_calls,
                repos.debug,
                repos.widget_states,
                repos.saved_widgets,
                repos.memory_index,
            ):
                repo.delete_by_session(session_id, cursor)
            self.delete(session_id, cursor=cursor)
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
            if row and (row['name'] == '' or row['name'] is None):
                cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,))
                count = cursor.fetchone()["COUNT(*)"]
                return count == 1
            return False
        except Exception:
            logger.exception("Failed to check should_rename for %s", session_id)
            return False


__all__ = ["SessionRepository"]
