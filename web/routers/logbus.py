"""LogBus API endpoints — query log events."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, HTTPException
from starlette.requests import Request

router = APIRouter(prefix="/api/logbus", tags=["logbus"])


def _get_logbus(request: Request):
    bus = getattr(request.app.state, "logbus", None)
    if bus is not None:
        return bus
    raise HTTPException(status_code=500, detail="LogBus not initialized")


@router.get("")
async def query_logs(
    request: Request,
    level: str | None = Query(None, description="Filter by level: ERROR, WARN, INFO, DEBUG"),
    module: str | None = Query(None, description="Filter by module prefix"),
    session_id: str | None = Query(None, description="Filter by session_id"),
    since: str | None = Query(None, description="ISO timestamp: only events after this"),
    until: str | None = Query(None, description="ISO timestamp: only events before this"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Query LogBus events with filters."""
    try:
        bus = _get_logbus(request)
    except Exception:
        return {"entries": [], "total": 0, "error": "LogBus not available"}

    entries = _read_jsonl_files(since=since, until=until)

    if level:
        entries = [e for e in entries if e.get("level") == level.upper()]
    if module:
        entries = [e for e in entries if e.get("module", "").startswith(module)]
    if session_id:
        entries = [e for e in entries if e.get("session_id") == session_id]

    total = len(entries)
    paged = entries[offset:offset + limit]

    return {"entries": paged, "total": total, "returned": len(paged), "offset": offset}


@router.get("/tail")
async def tail_logs(
    request: Request,
    lines: int = Query(50, ge=1, le=500, description="Number of recent lines"),
    level: str | None = Query(None, description="Filter by level"),
):
    """Tail recent log events (most recent first)."""
    try:
        bus = _get_logbus(request)
    except Exception:
        return {"entries": [], "source": "logbus"}

    entries = _read_jsonl_files()
    if level:
        entries = [e for e in entries if e.get("level") == level.upper()]
    entries.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return {"entries": entries[:lines], "source": "logbus"}


@router.get("/sessions/{session_id}")
async def session_logs(
    request: Request,
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get all LogBus events for a specific session."""
    try:
        bus = _get_logbus(request)
    except Exception:
        return {"session_id": session_id, "entries": [], "total": 0}

    entries = _read_jsonl_files()
    session_entries = [e for e in entries if e.get("session_id") == session_id]
    total = len(session_entries)
    paged = session_entries[offset:offset + limit]

    return {"session_id": session_id, "entries": paged, "total": total, "returned": len(paged)}


@router.delete("/cleanup")
async def cleanup_logs(
    older_than_days: int = Query(30, ge=1, description="Delete logs older than N days"),
):
    """Delete log files older than N days."""
    import glob
    import time

    log_dir = "logs/server"
    cutoff = time.time() - older_than_days * 86400
    deleted = 0

    for fpath in glob.glob(os.path.join(log_dir, "logbus_*.jsonl")):
        try:
            fname = os.path.basename(fpath)
            date_str = fname.replace("logbus_", "").replace(".jsonl", "")
            file_ts = datetime.strptime(date_str, "%Y%m%d").timestamp()
            if file_ts < cutoff:
                os.remove(fpath)
                deleted += 1
        except (ValueError, OSError):
            continue

    return {"deleted": deleted, "older_than_days": older_than_days}


def _read_jsonl_files(since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
    """Read LogBus JSONL files, most recent first."""
    import glob

    log_dir = "logs/server"
    files = sorted(glob.glob(os.path.join(log_dir, "logbus_*.jsonl")), reverse=True)

    since_ts: float | None = None
    until_ts: float | None = None
    if since:
        try:
            since_ts = datetime.fromisoformat(since).timestamp()
        except ValueError:
            pass
    if until:
        try:
            until_ts = datetime.fromisoformat(until).timestamp()
        except ValueError:
            pass

    entries: list[dict[str, Any]] = []
    for fpath in files[:5]:
        try:
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        import json
                        entry = json.loads(line)
                        ts = entry.get("ts", 0)
                        if since_ts and ts < since_ts:
                            continue
                        if until_ts and ts > until_ts:
                            continue
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue

    entries.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return entries
