"""Repository for Telegram message IDs — persists across bot restarts."""

from __future__ import annotations

import logging
from typing import Any

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class TelegramMsgIdRepo(_BaseRepository):
    _table_name = "telegram_msg_ids"

    async def save(self, chat_id: int, phase_key: str, msg_id: int) -> None:
        """Upsert a message ID for a (chat_id, phase_key) pair."""
        async with self._transaction() as conn:
            await conn.execute('''
                INSERT OR REPLACE INTO telegram_msg_ids (chat_id, phase_key, msg_id)
                VALUES (?, ?, ?)
            ''', (chat_id, phase_key, msg_id))

    async def get_all(self, chat_id: int) -> list[tuple[str, int]]:
        """Get all (phase_key, msg_id) pairs for a chat."""
        conn = await self._get_conn()
        cursor = await conn.execute('''
            SELECT phase_key, msg_id FROM telegram_msg_ids WHERE chat_id = ?
        ''', (chat_id,))
        rows = await cursor.fetchall()
        return [(row["phase_key"], row["msg_id"]) for row in rows]

    async def delete_chat(self, chat_id: int) -> None:
        """Delete all rows for a chat."""
        async with self._transaction() as conn:
            await conn.execute(
                "DELETE FROM telegram_msg_ids WHERE chat_id = ?", (chat_id,),
            )


__all__ = ["TelegramMsgIdRepo"]
