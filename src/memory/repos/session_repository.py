import logging
from datetime import datetime
from typing import Any, TYPE_CHECKING

from src.memory.repos.base import _BaseRepository

if TYPE_CHECKING:
    from src.memory.repos import Repositories

logger = logging.getLogger(__name__)


class SessionRepository(_BaseRepository):

    async def ensure(self, session_id: str) -> None:
        """Create a session row if it does not exist."""
        async with self._transaction() as conn:
            cursor = await conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
            if not await cursor.fetchone():
                await conn.execute(
                    "INSERT INTO sessions (session_id, name, created_at) VALUES (?, '', ?)",
                    (session_id, datetime.now().isoformat())
                )

    async def exists(self, session_id: str) -> bool:
        """Check if a session exists without creating it."""
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()
        return row is not None

    async def rename(self, session_id: str, name: str) -> None:
        """Rename a session."""
        async with self._transaction() as conn:
            await conn.execute("UPDATE sessions SET name = ? WHERE session_id = ?", (name, session_id))

    async def delete(self, session_id: str, cursor: Any = None) -> None:
        """Delete the session row itself."""
        if cursor is not None:
            await cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        else:
            async with self._transaction() as conn:
                await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    async def delete_cascade(self, session_id: str, repos: "Repositories") -> None:
        """Delete a session and all related rows in one transaction."""
        async with self._transaction() as conn:
            await conn.execute("DELETE FROM widget_versions WHERE session_id = ?", (session_id,))
            for repo in (
                repos.messages,
                repos.tool_calls,
                repos.debug,
                repos.widget_states,
                repos.saved_widgets,
                repos.memory_index,
            ):
                await repo.delete_by_session(session_id, conn)
            await self.delete(session_id, cursor=conn)

    async def get_all(self, limit: int = 50) -> list[tuple[Any, ...]]:
        """Return all sessions with summary data."""
        try:
            conn = await self._get_conn()
            cursor = await conn.execute('''
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
            return await cursor.fetchall()
        except Exception:
            logger.exception("Failed to get all sessions")
            return []

    async def check_should_rename(self, session_id: str) -> bool:
        """Check if the session should be auto-renamed (single user message, no name set)."""
        try:
            conn = await self._get_conn()
            cursor = await conn.execute("SELECT name FROM sessions WHERE session_id = ?", (session_id,))
            row = await cursor.fetchone()
            if row and (row['name'] == '' or row['name'] is None):
                cursor = await conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,))
                row = await cursor.fetchone()
                count = row[0] if row else 0
                return count == 1
            return False
        except Exception:
            logger.exception("Failed to check should_rename for %s", session_id)
            return False


__all__ = ["SessionRepository"]


__all__ = ["SessionRepository"]
