from datetime import datetime
import json
from src.memory.database import get_conn

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
