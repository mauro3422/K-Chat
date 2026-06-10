import json
import logging
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class DebugRepository(_BaseRepository):

    def save_info(self, session_id: str, data: dict[str, Any]) -> None:
        """Save or replace debug info for a session."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO debug_info (session_id, model, reasoning, system_prompt, tool_calls, history_before, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                data.get("model", ""),
                data.get("reasoning", ""),
                data.get("system_prompt", ""),
                json.dumps(data.get("tool_calls", []), ensure_ascii=False),
                json.dumps(data.get("history_before", []), ensure_ascii=False),
                datetime.now().isoformat()
            ))

    def delete_by_session(self, session_id: str, cursor: Any = None) -> None:
        """Delete debug info for a session. Pass cursor for atomic orchestration."""
        if cursor is not None:
            cursor.execute("DELETE FROM debug_info WHERE session_id = ?", (session_id,))
        else:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM debug_info WHERE session_id = ?", (session_id,))

    def get_info(self, session_id: str) -> dict[str, Any]:
        """Retrieve debug info for a session."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT model, reasoning, system_prompt, tool_calls, history_before
                FROM debug_info
                WHERE session_id = ?
            ''', (session_id,))
            row = cursor.fetchone()
            if not row:
                return {}
            model, reasoning, system_prompt, tool_calls, history_before = row
            return {
                "model": model,
                "reasoning": reasoning,
                "system_prompt": system_prompt,
                "tool_calls": json.loads(tool_calls) if tool_calls else [],
                "history_before": json.loads(history_before) if history_before else [],
            }
        except Exception:
            logger.exception("Failed to get debug info for %s", session_id)
            return {}


__all__ = ["DebugRepository"]
