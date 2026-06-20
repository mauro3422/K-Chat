import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from web.services.file_logger import get_server_log_dir, get_client_log_dir

router = APIRouter()
logger = logging.getLogger(__name__)


class ClientLogEntry(BaseModel):
    t: str
    l: str
    m: str
    msg: str
    d: Optional[dict | str | list] = None


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
    path = _resolve_log_path(get_server_log_dir(), date)
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
    path = _resolve_log_path(get_client_log_dir(), date)
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
    get_client_log_dir().mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = get_client_log_dir() / f"{date_str}.jsonl"

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
    source: str = Query("server", pattern="^(server|client|all)$"),
):
    """Tail the latest JSONL log files (like tail -f but one-shot), merged with LogBus.

    Returns entries from both file_logger and LogBus, sorted by timestamp descending.
    """
    path: Optional[Path] = None
    entries: list[dict] = []
    if source == "server":
        log_dir = get_server_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        path = _latest_log_path(log_dir)
        entries = _tail_file(path, lines) if path else []
    elif source == "client":
        log_dir = get_client_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        path = _latest_log_path(log_dir)
        entries = _tail_file(path, lines) if path else []
    else:
        server_path = _latest_log_path(get_server_log_dir())
        client_path = _latest_log_path(get_client_log_dir())
        entries = []
        if server_path:
            entries.extend(_tail_file(server_path, lines))
        if client_path:
            entries.extend(_tail_file(client_path, lines))
        entries.extend(_tail_gateway_logs(lines))
        entries.extend(_tail_logbus_logs(lines))

    if source == "server":
        entries.extend(_tail_logbus_logs(lines))
    elif source == "client":
        entries.extend(_tail_logbus_logs(lines))

    from datetime import datetime
    def _sort_key(entry: dict):
        val = entry.get("t") or entry.get("ts") or 0
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                # Try ISO format
                dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
                return dt.timestamp()
            except (ValueError, TypeError):
                pass
        return 0.0

    merged = sorted(entries, key=_sort_key, reverse=True)[:lines]

    return {
        "date": path.stem if path else "",
        "source": source,
        "entries": merged,
        "returned": len(merged),
    }


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


def _tail_gateway_logs(lines: int) -> list[dict]:
    try:
        from src.gateway_log import get_recent_logs
        entries = []
        for item in get_recent_logs(lines):
            detail = item.get('detail', '')
            event = item.get('event', '')
            message = f"{event}: {detail}".strip(": ").strip()
            entries.append({
                "t": item.get("ts", ""),
                "l": item.get("level", "INFO")[0:1],
                "m": f"gateway.{item.get('service', 'gateway')}",
                "msg": message,
                "d": item.get("meta", {}),
                "source": "gateway",
            })
        return entries
    except Exception:
        return []


def _tail_logbus_logs(lines: int) -> list[dict]:
    try:
        logbus_dir = Path("logs/server")
        logbus_files = sorted(logbus_dir.glob("logbus_*.jsonl"))
        if logbus_files:
            return _tail_file(logbus_files[-1], lines)
    except Exception:
        logger.warning("Failed to tail logbus logs", exc_info=True)
    return []


MAX_LOG_ENTRIES = 10000


def _read_filter(path: Path, level: Optional[str], module: Optional[str]) -> list[dict]:
    lines = _tail_lines(path, MAX_LOG_ENTRIES)
    entries = []
    for line in lines:
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


def _tail_lines(path: Path, n: int) -> list[str]:
    """Read the last n lines from a file efficiently."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            block_size = min(size, max(8192, n * 256))
            f.seek(max(0, size - block_size))
            data = f.read()
            lines = data.split(b"\n")
            result = [l.decode("utf-8", errors="replace") for l in lines if l]
            while len(result) < n and f.tell() < size:
                block_size = min(size - f.tell(), max(8192, n * 256))
                data = f.read(block_size)
                if not data:
                    break
                more = data.split(b"\n")
                result = [l.decode("utf-8", errors="replace") for l in more if l] + result
            return result[-n:]
    except Exception:
        return []


def _tail_file(path: Path, n: int) -> list[dict]:
    """Read the last n JSON lines from a file efficiently."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception:
        return []
    entries = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
