import json
import logging
from datetime import datetime
from typing import Any

from src.memory.repos.base import _BaseRepository

logger = logging.getLogger(__name__)


class DebugRepository(_BaseRepository):
    _table_name = "debug_info"

    async def save_info(self, session_id: str, data: dict[str, Any]) -> None:
        """Save or replace debug info for a session."""
        async with self._transaction() as conn:
            await conn.execute('''
                INSERT OR REPLACE INTO debug_info (session_id, model, reasoning, system_prompt, tool_calls, history_before, asr_telemetry, auto_memories, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                data.get("model", ""),
                data.get("reasoning", ""),
                data.get("system_prompt", ""),
                json.dumps(data.get("tool_calls", []), ensure_ascii=False),
                json.dumps(data.get("history_before", []), ensure_ascii=False),
                json.dumps(data.get("asr_telemetry", []), ensure_ascii=False),
                data.get("auto_memories", ""),
                datetime.now().isoformat()
            ))

    async def get_info(self, session_id: str) -> dict[str, Any]:
        """Retrieve debug info for a session."""
        try:
            conn = await self._get_conn()
            cursor = await conn.execute('''
                SELECT model, reasoning, system_prompt, tool_calls, history_before, asr_telemetry, auto_memories
                FROM debug_info
                WHERE session_id = ?
            ''', (session_id,))
            row = await cursor.fetchone()
            if not row:
                return {}
            model = row["model"]
            reasoning = row["reasoning"]
            system_prompt = row["system_prompt"]
            tool_calls = row["tool_calls"]
            history_before = row["history_before"]
            asr_telemetry = row["asr_telemetry"]
            auto_memories = row["auto_memories"] if "auto_memories" in row.keys() else ""
            return {
                "model": model,
                "reasoning": reasoning,
                "system_prompt": system_prompt,
                "tool_calls": json.loads(tool_calls) if tool_calls else [],
                "history_before": json.loads(history_before) if history_before else [],
                "asr_telemetry": json.loads(asr_telemetry) if asr_telemetry else [],
                "auto_memories": auto_memories,
            }
        except Exception:
            logger.exception("Failed to get debug info for %s", session_id)
            return {}

    async def append_asr_telemetry(self, session_id: str, event: dict[str, Any]) -> None:
        """Append an ASR telemetry event, keeping the last 100 entries."""
        info = await self.get_info(session_id)
        telemetry = info.get("asr_telemetry") or []
        if not isinstance(telemetry, list):
            telemetry = []
        telemetry.append(event)
        if len(telemetry) > 100:
            telemetry = telemetry[-100:]
        info["asr_telemetry"] = telemetry
        await self.save_info(session_id, info)


__all__ = ["DebugRepository"]
