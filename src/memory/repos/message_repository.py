import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


@dataclass
class MessageRecord:
    session_id: str = ""
    role: str = ""
    content: str = ""
    model: str | None = None
    reasoning: str = ""
    phases: str = "[]"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tool_calls: str | None = None
    tool_call_id: str | None = None


class MessageRepository(_BaseRepository):
    _table_name = "messages"

    def save(
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
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
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

    def save_record(self, record: MessageRecord) -> None:
        """Save a MessageRecord dataclass to the database."""
        self.save(
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

    def get_session_messages(self, session_id: str, limit: int = 500) -> list[tuple[Any, ...]]:
        """Retrieve messages for a session, ordered by creation time."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT role, content, model, created_at, reasoning, phases, tool_calls, tool_call_id
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
            ''', (session_id, limit))
            return cursor.fetchall()
        except Exception:
            logger.exception("Failed to get session messages for %s", session_id)
            return []


__all__ = ["MessageRecord", "MessageRepository"]
