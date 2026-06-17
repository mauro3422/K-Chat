"""Chat Journal — summarized log of each chat turn.

Stores a lightweight summary of every user-assistant interaction:
- First 100 chars of user message
- First 100 chars of assistant response
- Tools used (names + status, not payloads)
- Duration, model, token count
- Error if any

Queryable for quick overview without loading full message payloads.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.memory.db_path import resolve_db_path

logger = logging.getLogger("chat_journal")


def _get_conn() -> sqlite3.Connection:
    db_path = resolve_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def log_turn(
    session_id: str,
    user_msg: str,
    assistant_msg: str,
    tools_used: list[dict[str, Any]] | None = None,
    model: str = "",
    duration_ms: int = 0,
    token_count: int = 0,
    error: str = "",
) -> None:
    """Log a summarized chat turn to the journal."""
    tools_summary = []
    for t in (tools_used or []):
        tools_summary.append({
            "name": t.get("tool_name", t.get("name", "?")),
            "status": t.get("status", "ok"),
        })
    try:
        from src.logbus import LogEvent, get_logbus
        bus = get_logbus()
        bus.emit(LogEvent(
            level="INFO",
            module="chat.journal",
            msg="chat_turn",
            session_id=session_id,
            duration_ms=duration_ms,
            data={
                "user_msg": (user_msg or "")[:200],
                "assistant_msg": (assistant_msg or "")[:200],
                "tools_used": tools_summary,
                "model": model,
                "token_count": token_count,
                "error": (error or "")[:500],
            },
        ))
    except Exception:
        pass
    try:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO chat_journal
                   (ts, session_id, user_msg, assistant_msg, tools_used, model, duration_ms, token_count, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    session_id,
                    (user_msg or "")[:200],
                    (assistant_msg or "")[:200],
                    json.dumps(tools_summary, ensure_ascii=False),
                    model,
                    duration_ms,
                    token_count,
                    error[:500] if error else "",
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to write chat journal: %s", e)


def get_session_journal(session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get journal entries for a session."""
    try:
        conn = _get_conn()
        try:
            cursor = conn.execute(
                """SELECT ts, user_msg, assistant_msg, tools_used, model,
                          duration_ms, token_count, error
                   FROM chat_journal WHERE session_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            )
            return [
                {
                    "ts": row["ts"],
                    "user_msg": row["user_msg"],
                    "assistant_msg": row["assistant_msg"],
                    "tools_used": json.loads(row["tools_used"]) if row["tools_used"] else [],
                    "model": row["model"],
                    "duration_ms": row["duration_ms"],
                    "token_count": row["token_count"],
                    "error": row["error"],
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to query chat journal: %s", e)
        return []


def get_all_journal(limit: int = 100) -> list[dict[str, Any]]:
    """Get recent journal entries across all sessions."""
    try:
        conn = _get_conn()
        try:
            cursor = conn.execute(
                """SELECT ts, session_id, user_msg, assistant_msg, tools_used,
                          model, duration_ms, token_count, error
                   FROM chat_journal ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            return [
                {
                    "ts": row["ts"],
                    "session_id": row["session_id"],
                    "user_msg": row["user_msg"],
                    "assistant_msg": row["assistant_msg"],
                    "tools_used": json.loads(row["tools_used"]) if row["tools_used"] else [],
                    "model": row["model"],
                    "duration_ms": row["duration_ms"],
                    "token_count": row["token_count"],
                    "error": row["error"],
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to query chat journal: %s", e)
        return []


def cleanup_old_entries(days: int = 30) -> int:
    """Delete journal entries older than N days."""
    try:
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM chat_journal WHERE ts < datetime('now', ?)",
                (f"-{days} days",),
            )
            count = cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to cleanup chat journal: %s", e)
        return 0
