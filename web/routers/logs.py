import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from web.services.file_logger import SERVER_LOG_DIR, CLIENT_LOG_DIR

router = APIRouter()
logger = logging.getLogger(__name__)


class ClientLogEntry(BaseModel):
    t: str
    l: str
    m: str
    msg: str
    d: Optional[dict] = None


@router.get("/api/logs")
def query_logs(
    level: Optional[str] = Query(None, description="Filter: D, I, W, E"),
    module: Optional[str] = Query(None, description="Filter by module name"),
    date: Optional[str] = Query(None, description="YYYYMMDD (defaults to today)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Query server-side structured logs from JSONL files.

    Returns matching entries sorted by timestamp (newest first).
    """
    path = _resolve_log_path(SERVER_LOG_DIR, date)
    if not path or not path.exists():
        return {"entries": [], "total": 0}

    entries = _read_filter(path, level, module)

    # Filter by date if specified
    if date:
        entries = [e for e in entries if e.get("t", "").startswith(date[:8])]

    total = len(entries)
    # Reverse so newest (appended last) appear first
    entries.reverse()
    sliced = entries[offset: offset + limit]
    return {"date": path.stem, "entries": sliced, "total": total, "returned": len(sliced)}


@router.get("/api/logs/client")
def query_client_logs(
    level: Optional[str] = Query(None, description="Filter: D, I, W, E"),
    module: Optional[str] = Query(None, description="Filter by module name"),
    date: Optional[str] = Query(None, description="YYYYMMDD"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Query client-submitted logs (sent from browser)."""
    path = _resolve_log_path(CLIENT_LOG_DIR, date)
    if not path or not path.exists():
        return {"entries": [], "total": 0}

    entries = _read_filter(path, level, module)
    total = len(entries)
    entries.reverse()
    sliced = entries[offset: offset + limit]
    return {"date": path.stem, "entries": sliced, "total": total, "returned": len(sliced)}


@router.post("/api/logs/client")
def ingest_client_logs(entries: list[ClientLogEntry]):
    """Persist client-submitted log entries to a JSONL file."""
    CLIENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = CLIENT_LOG_DIR / f"{date_str}.jsonl"

    count = 0
    with open(path, "a") as f:
        for entry in entries:
            f.write(entry.model_dump_json(exclude_none=True) + "\n")
            count += 1

    logger.info("ingested %d client log entries", count)
    return {"ok": True, "count": count}


@router.get("/api/logs/tail")
def tail_logs(
    lines: int = Query(50, ge=1, le=500),
    source: str = Query("server", pattern="^(server|client)$"),
):
    """Tail the latest JSONL log file (like tail -f but one-shot)."""
    log_dir = SERVER_LOG_DIR if source == "server" else CLIENT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    path = _latest_log_path(log_dir)
    if not path:
        return {"entries": [], "source": source}

    entries = _tail_file(path, lines)
    return {"date": path.stem, "source": source, "entries": entries, "returned": len(entries)}


# ---- helpers ----


def _resolve_log_path(log_dir: Path, date: Optional[str]) -> Optional[Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    if date:
        p = log_dir / f"{date}.jsonl"
        return p if p.exists() else None
    return _latest_log_path(log_dir)


def _latest_log_path(log_dir: Path) -> Optional[Path]:
    files = sorted(log_dir.glob("*.jsonl"))
    return files[-1] if files else None


def _read_filter(path: Path, level: Optional[str], module: Optional[str]) -> list[dict]:
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if level and entry.get("l") != level:
                continue
            if module and entry.get("m") != module:
                continue
            entries.append(entry)
    return entries


def _tail_file(path: Path, n: int) -> list[dict]:
    """Read the last n JSON lines from a file efficiently."""
    entries = []
    try:
        with open(path) as f:
            # Read file backwards for last n lines
            f.seek(0, 2)
            pos = f.tell()
            buf = ""
            while pos >= 0 and len(entries) < n:
                f.seek(pos)
                chunk = f.read(max(2048, n * 256))
                lines = chunk.split("\n")
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if len(entries) >= n:
                        break
                pos -= len(chunk)
                if pos < 0:
                    break
    except Exception:
        return []
    entries.reverse()
    return entries[-n:]
