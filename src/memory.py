import sqlite3
import os
import json
from datetime import datetime
from config import MEMORY_DB_PATH


def get_conn():
    db_path = os.getenv('MEMORY_DB_PATH', MEMORY_DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn



def init_db():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                model TEXT,
                reasoning TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        ''')
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN reasoning TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                input TEXT NOT NULL,
                status TEXT NOT NULL,
                turn INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        ''')
        try:
            cursor.execute("ALTER TABLE tool_calls ADD COLUMN turn INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN phases TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debug_info (
                session_id TEXT PRIMARY KEY,
                model TEXT,
                reasoning TEXT,
                system_prompt TEXT,
                tool_calls TEXT,
                history_before TEXT,
                updated_at TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS widget_states (
                session_id TEXT NOT NULL,
                widget_id TEXT NOT NULL,
                state TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_id, widget_id)
            )
        ''')
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN completion_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN total_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_session_id ON tool_calls (session_id)")

        conn.commit()
    finally:
        conn.close()


def save_widget_state(session_id: str, widget_id: str, state: str) -> None:
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO widget_states (session_id, widget_id, state, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, widget_id) DO UPDATE SET
                state = excluded.state,
                updated_at = excluded.updated_at
        ''', (session_id, widget_id, state, datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()


def get_widget_states(session_id: str) -> dict:
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT widget_id, state FROM widget_states WHERE session_id = ?', (session_id,))
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        conn.close()


def save_message(session_id, role, content, model=None, reasoning="", phases="[]", prompt_tokens=0, completion_tokens=0, total_tokens=0):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (session_id, role, content, model, reasoning, phases, prompt_tokens, completion_tokens, total_tokens, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, role, content, model, reasoning, phases, prompt_tokens, completion_tokens, total_tokens, datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()


def get_history(session_id, limit=50):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content, model, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (session_id, limit))
        return cursor.fetchall()
    finally:
        conn.close()


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


def log_tool_call(session_id: str, tool_name: str, input_str: str, status: str, turn: int = 0):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tool_calls (session_id, tool_name, input, status, turn, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, tool_name, input_str, status, turn, datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()


def get_tool_history(session_id: str, limit: int = 10) -> list:
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tool_name, input, status, created_at, turn
            FROM tool_calls
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (session_id, limit))
        return cursor.fetchall()
    finally:
        conn.close()


def ensure_session(session_id: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO sessions (session_id, name, created_at) VALUES (?, '', ?)",
                (session_id, datetime.now().isoformat())
            )
        conn.commit()
    finally:
        conn.close()


def rename_session(session_id: str, name: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET name = ? WHERE session_id = ?", (name, session_id))
        conn.commit()
    finally:
        conn.close()


def check_should_rename(session_id: str) -> bool:
    """Retorna True si el nombre de la sesión está vacío y tiene exactamente 1 mensaje de usuario."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if row and (row[0] == '' or row[0] is None):
            cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,))
            count = cursor.fetchone()[0]
            return count == 1
        return False
    finally:
        conn.close()


def delete_session(session_id: str):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM tool_calls WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def get_sessions(limit: int = 50) -> list:
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.session_id,
                   MIN(m.created_at),
                   MAX(m.created_at),
                   COUNT(*),
                   SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END),
                   COALESCE(s.name, '')
            FROM messages m
            LEFT JOIN sessions s ON m.session_id = s.session_id
            GROUP BY m.session_id
            ORDER BY MAX(m.created_at) DESC
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_session_messages(session_id: str, limit: int = 200) -> list:
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content, model, created_at, reasoning, phases
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
        ''', (session_id, limit))
        return cursor.fetchall()
    finally:
        conn.close()
