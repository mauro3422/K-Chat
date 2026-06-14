"""Gateway structured logging to SQLite DB.

All gateway events (startup, shutdown, health checks, crashes, signal handling)
are stored in the gateway_log table for easy querying and cleanup.

Uses synchronous sqlite3 writes — no async overhead, writes complete immediately.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.memory.db_path import resolve_db_path

logger = logging.getLogger("gateway.db")


def _get_conn() -> sqlite3.Connection:
    db_path = resolve_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def log_event(
    level: str,
    service: str,
    event: str,
    detail: str = "",
    pid: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    try:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO gateway_log (ts, level, service, event, detail, pid, meta) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    level,
                    service,
                    event,
                    detail,
                    pid,
                    json.dumps(meta or {}),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to write gateway log: %s", e)


def log_startup(service: str, detail: str = "", pid: int | None = None) -> None:
    log_event("INFO", service, "startup", detail, pid)


def log_shutdown(service: str, detail: str = "") -> None:
    log_event("INFO", service, "shutdown", detail)


def log_health_ok(service: str, latency_ms: float) -> None:
    log_event("INFO", service, "health_ok", meta={"latency_ms": latency_ms})


def log_health_fail(service: str, detail: str = "") -> None:
    log_event("WARN", service, "health_fail", detail)


def log_crash(service: str, detail: str = "", pid: int | None = None) -> None:
    log_event("ERROR", service, "crash", detail, pid)


def log_signal(signal_name: str, detail: str = "") -> None:
    log_event("INFO", "gateway", f"signal_{signal_name}", detail)


def log_uptime(services: dict[str, dict[str, Any]], uptime_s: float) -> None:
    log_event("INFO", "gateway", "heartbeat", meta={
        "uptime_s": round(uptime_s, 1),
        "services": {
            name: {"running": info.get("running", False)}
            for name, info in services.items()
        },
    })


def get_recent_logs(limit: int = 50) -> list[dict[str, Any]]:
    try:
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "SELECT ts, level, service, event, detail, pid, meta FROM gateway_log ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [
                {
                    "ts": row["ts"],
                    "level": row["level"],
                    "service": row["service"],
                    "event": row["event"],
                    "detail": row["detail"],
                    "pid": row["pid"],
                    "meta": json.loads(row["meta"]) if row["meta"] else {},
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to query gateway logs: %s", e)
        return []


def cleanup_old_logs(days: int = 7) -> int:
    try:
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM gateway_log WHERE ts < datetime('now', ?)",
                (f"-{days} days",),
            )
            count = cursor.rowcount
            conn.commit()
            conn.close()
            return count
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to cleanup gateway logs: %s", e)
        return 0
