import logging
from datetime import datetime

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class WidgetStateRepository(_BaseRepository):

    def save_state(self, session_id: str, widget_id: str, state: str) -> None:
        """Save or update a widget state."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO widget_states (session_id, widget_id, state, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, widget_id) DO UPDATE SET
                    state = excluded.state,
                    updated_at = excluded.updated_at
            ''', (session_id, widget_id, state, datetime.now().isoformat()))

    def get_states(self, session_id: str) -> dict[str, str]:
        """Retrieve all widget states for a session."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('SELECT widget_id, state FROM widget_states WHERE session_id = ?', (session_id,))
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception:
            logger.exception("Failed to get widget states for %s", session_id)
            return {}


__all__ = ["WidgetStateRepository"]
