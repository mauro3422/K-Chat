"""Persistent LAN bridge for work delegated from Kairos to Codex.

This is not an auto-executor. It is a small, auditable handoff channel:
Kairos creates a task, Codex claims/runs it from the PC grande, and the result
is written back for Kairos to read.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any


TASK_STATUSES = {"open", "running", "done", "failed", "cancelled"}
MESSAGE_ROLES = {"kairos", "codex", "system"}
PRIORITIES = {"low", "normal", "high", "urgent"}


def default_bridge_path(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[2]
    return base / ".kairos" / "codex-bridge" / "tasks.json"


def _clean_text(value: str, *, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    return cleaned[:limit]


def _read_tasks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_tasks(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _message(role: str, content: str, source: str = "") -> dict[str, Any]:
    clean_role = role if role in MESSAGE_ROLES else "system"
    return {
        "role": clean_role,
        "content": str(content or "").strip()[:12000],
        "source": _clean_text(source, limit=120),
        "created_at": time.time(),
    }


def create_task(
    *,
    title: str,
    prompt: str,
    from_node: str = "",
    session_id: str = "",
    priority: str = "normal",
    path: Path | None = None,
) -> dict[str, Any]:
    clean_title = _clean_text(title, limit=160)
    clean_prompt = str(prompt or "").strip()[:12000]
    if not clean_title:
        raise ValueError("title is required")
    if not clean_prompt:
        raise ValueError("prompt is required")

    now = time.time()
    task = {
        "id": f"ctx-{uuid.uuid4().hex[:12]}",
        "title": clean_title,
        "from_node": _clean_text(from_node, limit=80),
        "session_id": _clean_text(session_id, limit=120),
        "priority": priority if priority in PRIORITIES else "normal",
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "claimed_by": "",
        "messages": [_message("kairos", clean_prompt, source=from_node)],
    }
    bridge_path = path or default_bridge_path()
    tasks = _read_tasks(bridge_path)
    tasks.append(task)
    _write_tasks(bridge_path, tasks)
    return task


def list_tasks(
    *,
    status: str = "open",
    limit: int = 50,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    tasks = _read_tasks(path or default_bridge_path())
    if status and status != "all":
        tasks = [task for task in tasks if task.get("status") == status]
    tasks.sort(key=lambda task: float(task.get("updated_at") or 0), reverse=True)
    return tasks[: max(1, min(int(limit or 50), 200))]


def get_task(task_id: str, *, path: Path | None = None) -> dict[str, Any] | None:
    for task in _read_tasks(path or default_bridge_path()):
        if task.get("id") == task_id:
            return task
    return None


def update_task(
    task_id: str,
    *,
    status: str | None = None,
    message: str = "",
    role: str = "codex",
    source: str = "codex",
    claimed_by: str = "",
    path: Path | None = None,
) -> dict[str, Any] | None:
    if status is not None and status not in TASK_STATUSES:
        raise ValueError(f"invalid status: {status}")
    bridge_path = path or default_bridge_path()
    tasks = _read_tasks(bridge_path)
    for task in tasks:
        if task.get("id") != task_id:
            continue
        if status is not None:
            task["status"] = status
        if claimed_by:
            task["claimed_by"] = _clean_text(claimed_by, limit=120)
        if message.strip():
            messages = task.setdefault("messages", [])
            if isinstance(messages, list):
                messages.append(_message(role, message, source=source))
        task["updated_at"] = time.time()
        _write_tasks(bridge_path, tasks)
        return task
    return None
