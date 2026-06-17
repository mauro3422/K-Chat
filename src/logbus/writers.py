"""LogBus writers: JsonlWriter, ConsoleWriter."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime

from src.logbus.models import LogEvent
from src.logbus.core import BaseWriter

logger = logging.getLogger(__name__)


class JsonlWriter(BaseWriter):
    """Write LogEvents to JSONL files, one file per day."""

    def __init__(self, log_dir: str = "logs/server") -> None:
        self._log_dir = log_dir
        self._current_file: str | None = None
        self._fh: object | None = None
        self._cleanup_old_files()

    def _cleanup_old_files(self, max_days: int = 30) -> None:
        """Delete log files older than max_days."""
        import time
        import glob

        cutoff = time.time() - max_days * 86400
        log_dir = self._log_dir
        if not os.path.isdir(log_dir):
            return

        for fpath in glob.glob(os.path.join(log_dir, "logbus_*.jsonl")):
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
            except OSError:
                pass

    async def write(self, events: list[LogEvent]) -> None:
        filepath = self._get_filepath()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        lines = "\n".join(self._serialize(e) for e in events) + "\n"

        def _sync_write():
            with open(filepath, mode="a") as f:
                f.write(lines)

        await asyncio.to_thread(_sync_write)

    def _get_filepath(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        return os.path.join(self._log_dir, f"logbus_{today}.jsonl")

    def _serialize(self, event: LogEvent) -> str:
        from datetime import datetime
        return json.dumps({
            "ts": event.ts,
            "level": event.level,
            "module": event.module,
            "msg": event.msg,
            "session_id": event.session_id,
            "request_id": event.request_id,
            "data": event.data,
            "duration_ms": event.duration_ms,
        }, ensure_ascii=False, default=str)


class ConsoleWriter(BaseWriter):
    """Write LogEvents to stderr (useful for --verbose mode)."""

    LEVEL_EMOJI = {
        "ERROR": "🔴",
        "WARN": "🟡",
        "INFO": "🟢",
        "DEBUG": "⚪",
    }

    async def write(self, events: list[LogEvent]) -> None:
        for e in events:
            emoji = self.LEVEL_EMOJI.get(e.level, "⚪")
            sid = f"[{e.session_id[:8]}] " if e.session_id else ""
            dur = f" ({e.duration_ms:.0f}ms)" if e.duration_ms else ""
            print(f"{emoji} {sid}{e.module}: {e.msg}{dur}")


class SqliteWriter(BaseWriter):
    """Write LogEvents to a SQLite table for fast querying."""

    def __init__(self, db_path: str = "data/logbus.db") -> None:
        self._db_path = db_path
        self._init_table()

    def _init_table(self) -> None:
        import sqlite3
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logbus_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                level TEXT NOT NULL,
                module TEXT NOT NULL,
                msg TEXT NOT NULL,
                session_id TEXT,
                request_id TEXT,
                data TEXT,
                duration_ms REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logbus_ts ON logbus_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logbus_level ON logbus_events(level)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logbus_session ON logbus_events(session_id)")
        # Cleanup old entries (older than 30 days)
        try:
            import time
            cutoff_ts = time.time() - 30 * 86400
            conn.execute("DELETE FROM logbus_events WHERE ts < ?", (cutoff_ts,))
            conn.commit()
        except Exception:
            pass
        conn.commit()
        conn.close()

    async def write(self, events: list[LogEvent]) -> None:
        import sqlite3
        import json
        conn = sqlite3.connect(self._db_path)
        try:
            rows = [(
                e.ts, e.level, e.module, e.msg,
                e.session_id, e.request_id,
                json.dumps(e.data) if e.data else None,
                e.duration_ms,
            ) for e in events]
            conn.executemany(
                "INSERT INTO logbus_events (ts, level, module, msg, session_id, request_id, data, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    async def flush(self) -> None:
        pass
