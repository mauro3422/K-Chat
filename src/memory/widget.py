from datetime import datetime
from src.memory.database import get_conn

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
