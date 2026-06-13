import logging
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class SavedWidgetRepository(_BaseRepository):
    _table_name = "saved_widgets"

    def save(self, session_id: str, widget_id: str, code: str, description: str = "") -> dict[str, Any]:
        """Save a widget version and update the active widget record."""
        with self._transaction() as conn:
            now = datetime.now().isoformat()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO widget_versions (widget_id, version, code, description, session_id, created_at)
                VALUES (?, COALESCE((SELECT MAX(version) + 1 FROM widget_versions WHERE widget_id = ?), 1), ?, ?, ?, ?)
            ''', (widget_id, widget_id, code, description, session_id, now))
            cursor.execute(
                'SELECT MAX(version) FROM widget_versions WHERE widget_id = ?',
                (widget_id,)
            )
            next_version = cursor.fetchone()["MAX(version)"]
            cursor.execute('''
                INSERT INTO saved_widgets (session_id, widget_id, code, version, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(widget_id) DO UPDATE SET
                    code = excluded.code,
                    version = excluded.version,
                    description = excluded.description,
                    updated_at = excluded.updated_at,
                    session_id = excluded.session_id
            ''', (session_id, widget_id, code, next_version, description, now, now))
        return {"widget_id": widget_id, "version": next_version, "status": "saved"}

    def delete_by_session(self, session_id: str, cursor: Any = None) -> None:
        """Delete saved widgets and versions for a session. Pass cursor for atomic orchestration."""
        if cursor is not None:
            cursor.execute("DELETE FROM widget_versions WHERE widget_id IN (SELECT widget_id FROM saved_widgets WHERE session_id = ?)", (session_id,))
            cursor.execute("DELETE FROM saved_widgets WHERE session_id = ?", (session_id,))
        else:
            with self._transaction() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM widget_versions WHERE widget_id IN (SELECT widget_id FROM saved_widgets WHERE session_id = ?)", (session_id,))
                cur.execute("DELETE FROM saved_widgets WHERE session_id = ?", (session_id,))

    def get(self, widget_id: str) -> dict[str, Any] | None:
        """Get the active version of a widget."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT code, version, description, updated_at FROM saved_widgets WHERE widget_id = ?',
                (widget_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "widget_id": widget_id,
                    "code": row["code"],
                    "version": row["version"],
                    "description": row["description"],
                    "updated_at": row["updated_at"]
                }
            return None
        except Exception:
            logger.exception("Failed to get widget %s", widget_id)
            return None

    def get_versions(self, widget_id: str) -> list[dict[str, Any]]:
        """Get all versions of a widget."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT version, description, created_at FROM widget_versions WHERE widget_id = ? ORDER BY version DESC',
                (widget_id,)
            )
            rows = cursor.fetchall()
            return [
                {
                    "version": row["version"],
                    "description": row["description"],
                    "created_at": row["created_at"]
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to get versions for widget %s", widget_id)
            return []

    def get_by_version(self, widget_id: str, version: int) -> dict[str, Any] | None:
        """Get a specific version of a widget."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT code, description, created_at FROM widget_versions WHERE widget_id = ? AND version = ?',
                (widget_id, version)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "widget_id": widget_id,
                    "version": version,
                    "code": row["code"],
                    "description": row["description"],
                    "created_at": row["created_at"]
                }
            return None
        except Exception:
            logger.exception("Failed to get widget %s version %d", widget_id, version)
            return None


__all__ = ["SavedWidgetRepository"]
