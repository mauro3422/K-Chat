from datetime import datetime
from src.memory.database import get_conn

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
