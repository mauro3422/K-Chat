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
            # Ensure phases column exists (lazy migration for existing DBs)
            try:
                await conn.execute("ALTER TABLE debug_info ADD COLUMN phases TEXT DEFAULT '[]'")
            except Exception:
                logger.warning("Column phases may already exist in debug_info", exc_info=True)
            try:
                await conn.execute("ALTER TABLE debug_info ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
            except Exception:
                logger.warning("Column prompt_tokens may already exist in debug_info", exc_info=True)
            try:
                await conn.execute("ALTER TABLE debug_info ADD COLUMN completion_tokens INTEGER DEFAULT 0")
            except Exception:
                logger.warning("Column completion_tokens may already exist in debug_info", exc_info=True)
            try:
                await conn.execute("ALTER TABLE debug_info ADD COLUMN total_tokens INTEGER DEFAULT 0")
            except Exception:
                logger.warning("Column total_tokens may already exist in debug_info", exc_info=True)
            await conn.execute('''
                INSERT OR REPLACE INTO debug_info (session_id, model, reasoning, system_prompt, tool_calls, history_before, asr_telemetry, auto_memories, phases, prompt_tokens, completion_tokens, total_tokens, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                data.get("model", ""),
                data.get("reasoning", ""),
                data.get("system_prompt", ""),
                json.dumps(data.get("tool_calls", []), ensure_ascii=False),
                json.dumps(data.get("history_before", []), ensure_ascii=False),
                json.dumps(data.get("asr_telemetry", []), ensure_ascii=False),
                data.get("auto_memories", ""),
                data.get("phases", "[]"),
                data.get("prompt_tokens", 0),
                data.get("completion_tokens", 0),
                data.get("total_tokens", 0),
                datetime.now().isoformat()
            ))

    async def get_info(self, session_id: str) -> dict[str, Any]:
        """Retrieve debug info for a session."""
        try:
            async with self._connection() as conn:
                # Check if phases column exists
                col_info = await conn.execute("PRAGMA table_info(debug_info)")
                columns = {row[1] for row in await col_info.fetchall()}
                select_cols = "model, reasoning, system_prompt, tool_calls, history_before, asr_telemetry, auto_memories"
                if "phases" in columns:
                    select_cols += ", phases, prompt_tokens, completion_tokens, total_tokens"
                cursor = await conn.execute(f'''
                    SELECT {select_cols}
                    FROM debug_info
                    WHERE session_id = ?
                ''', (session_id,))
                row = await cursor.fetchone()
            if not row:
                return {}
            result = {
                "model": row["model"],
                "reasoning": row["reasoning"],
                "system_prompt": row["system_prompt"],
                "tool_calls": json.loads(row["tool_calls"]) if row["tool_calls"] else [],
                "history_before": json.loads(row["history_before"]) if row["history_before"] else [],
                "asr_telemetry": json.loads(row["asr_telemetry"]) if row["asr_telemetry"] else [],
                "auto_memories": row["auto_memories"] if "auto_memories" in row.keys() else "",
            }
            if "phases" in columns:
                result["phases"] = row["phases"] if "phases" in row.keys() else "[]"
                result["prompt_tokens"] = row["prompt_tokens"] if "prompt_tokens" in row.keys() else 0
                result["completion_tokens"] = row["completion_tokens"] if "completion_tokens" in row.keys() else 0
                result["total_tokens"] = row["total_tokens"] if "total_tokens" in row.keys() else 0
            return result
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
