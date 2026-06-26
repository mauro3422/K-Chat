import logging
from datetime import datetime

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class WidgetStateRepository(_BaseRepository):
    _table_name = "widget_states"

    async def save_state(self, session_id: str, widget_id: str, state: str) -> None:
        """Save or update a widget state."""
        async with self._transaction() as conn:
            await conn.execute('''
                INSERT INTO widget_states (session_id, widget_id, state, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, widget_id) DO UPDATE SET
                    state = excluded.state,
                    updated_at = excluded.updated_at
            ''', (session_id, widget_id, state, datetime.now().isoformat()))

    async def get_states(self, session_id: str) -> dict[str, str]:
        """Retrieve all widget states for a session."""
        try:
            conn = await self._get_conn()
            cursor = await conn.execute('SELECT widget_id, state FROM widget_states WHERE session_id = ?', (session_id,))
            rows = await cursor.fetchall()
            return {row["widget_id"]: row["state"] for row in rows}
        except Exception:
            logger.exception("Failed to get widget states for %s", session_id)
            return {}


__all__ = ["WidgetStateRepository"]
