from datetime import datetime
import json
from src.memory.database import get_conn

def save_debug_info(session_id: str, data: dict):
    conn = get_conn()
    try:
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
        conn.commit()
    finally:
        conn.close()

def get_debug_info(session_id: str) -> dict:
    conn = get_conn()
    try:
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
    finally:
        conn.close()
