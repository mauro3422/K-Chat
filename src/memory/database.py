import sqlite3
import os
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
