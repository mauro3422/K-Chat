from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from src.coordination.memory_lease import get_memory_lease_manager
from src.coordination.memory_write_queue import get_memory_write_queue
from web.routers._node_helpers import _get_coordinator, _get_event_bus


def _get_repos(request: Request):
    return getattr(request.app.state, "repos", None)


def _get_manage_memory_run(request: Request):
    runner = getattr(request.app.state, "manage_memory_run", None)
    if runner is None:
        raise RuntimeError("manage_memory runner not configured")
    return runner


def _get_queue(request: Request):
    return getattr(request.app.state, "memory_write_queue", None) or get_memory_write_queue()


def _get_lease_manager(request: Request):
    return getattr(request.app.state, "memory_lease_manager", None) or get_memory_lease_manager(getattr(request.app.state, "config", None))


async def _compare_memory(request: Request, key_pattern: str = "", fmt: str = "json") -> tuple[str, dict | None]:
    result = await _get_manage_memory_run(request)(
        operation="compare",
        key_pattern=key_pattern,
        fmt=fmt,
        _repos=_get_repos(request),
    )
    if fmt != "json":
        return result, None
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        parsed = {"raw": result}
    return result, parsed


def summarize_memory_compare(compare: dict[str, Any] | None) -> dict[str, Any]:
    compare = compare or {}
    only_in_md = list(compare.get("only_in_md", []) or [])
    only_in_db = list(compare.get("only_in_db", []) or [])
    mismatched = list(compare.get("mismatched", []) or [])
    rename_candidates = list(compare.get("rename_candidates", []) or [])

    ambiguous_renames = [item for item in rename_candidates if item.get("ambiguous")]
    actions: list[str] = []

    if only_in_md:
        actions.append("reconstruir memory.db desde MEMORY.md")
    if mismatched:
        actions.append("revisar valores desalineados entre MEMORY.md y memory.db")
    if only_in_db:
        if rename_candidates:
            actions.append("revisar posibles renombres antes de borrar orfanos")
        else:
            actions.append("eliminar entradas huérfanas de memory.db")
    if ambiguous_renames:
        actions.append("revisión manual de renombres ambiguos")
    if not actions:
        actions.append("sin conflicto aparente")

    severity = "clean"
    if ambiguous_renames or mismatched:
        severity = "high"
    elif only_in_md or only_in_db:
        severity = "medium"

    return {
        "severity": severity,
        "counts": {
            "only_in_md": len(only_in_md),
            "only_in_db": len(only_in_db),
            "mismatched": len(mismatched),
            "rename_candidates": len(rename_candidates),
            "ambiguous_renames": len(ambiguous_renames),
        },
        "actions": actions,
        "has_conflicts": bool(only_in_md or only_in_db or mismatched or ambiguous_renames),
    }


async def build_memory_snapshot(request: Request, key_pattern: str = "") -> dict[str, Any]:
    lease_manager = _get_lease_manager(request)
    lease = lease_manager.snapshot()
    queue = _get_queue(request)
    coordinator = _get_coordinator(request)
    coord_snapshot = coordinator.snapshot()
    compare_result, parsed = await _compare_memory(request, key_pattern=key_pattern, fmt="json")
    compare_summary = summarize_memory_compare(parsed)
    return {
        "ok": True,
        "lease": lease.to_dict() if lease else None,
        "queue_size": len(queue),
        "queue": queue.snapshot(),
        "queue_path": getattr(queue, "persistence_path", ""),
        "source": {
            "mode": "local",
            "node_id": coord_snapshot.get("node_id", ""),
            "role": coord_snapshot.get("role", ""),
        },
        "memory": {
            "revision": coord_snapshot.get("last_memory_revision", 0.0),
            "sync": coord_snapshot.get("last_memory_sync", 0.0),
            "is_fresh": coord_snapshot.get("memory_is_fresh", False),
        },
        "compare": parsed or {"raw": compare_result},
        "compare_summary": compare_summary,
    }


async def relay_memory_event(request: Request, event_type: str, event_data: Any) -> dict[str, Any]:
    bus = _get_event_bus(request)
    coordinator = _get_coordinator(request)
    source = event_data.get("source", {}) if isinstance(event_data, dict) else {}
    if event_type == "memory_updated":
        try:
            await coordinator.mark_memory_revision({"event": event_type, "source": source})
        except Exception:
            pass
    elif event_type == "memory_write_completed":
        try:
            await coordinator.mark_memory_revision({"event": event_type, "source": source})
            await coordinator.mark_memory_sync({"event": event_type, "source": source})
        except Exception:
            pass
    elif event_type in {"memory_synced", "memory_repaired"}:
        try:
            await coordinator.mark_memory_sync({"event": event_type, "source": source})
        except Exception:
            pass
    await bus.publish(event_type, event_data)
    return {"ok": True, "type": event_type}
