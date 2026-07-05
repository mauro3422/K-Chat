"""Review and resolve memory inbox groups."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from src.memory.curator.memory_inbox import load_memory_inbox
from src.memory.curator.curation_events import append_curation_decision
from src.memory.synthesis.morning_plan import coalesce_inbox_items

CanonicalWriter = Callable[[str, str], Awaitable[Any]]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _base(root: str | Path | None = None) -> Path:
    return Path(root) if root is not None else _project_root()


def _memory_target_id(key: str) -> str:
    return f"memory:{key.strip()}" if key.strip() else ""


def _inbox_relation_hints(
    inbox_ids: list[str],
    *,
    target_id: str,
    relation_type: str,
    group_id: str = "",
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for inbox_id in inbox_ids:
        source_id = f"inbox:{inbox_id}"
        hints.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "provenance": "memory_inbox_review",
            }
        )
    if group_id:
        hints.append(
            {
                "source_id": f"inbox_group:{group_id}",
                "target_id": target_id,
                "relation_type": relation_type,
                "provenance": "memory_inbox_group_review",
            }
        )
    return hints


def list_inbox_groups(
    root: str | Path | None = None,
    status: str = "pending",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List coalesced inbox groups for curator review."""

    items = load_memory_inbox(root=root, limit=max(limit * 4, limit))
    filtered = [
        item for item in items
        if not status or str(item.get("status", "pending")) == status
    ]
    return coalesce_inbox_items(filtered)[:limit]


def find_inbox_group(
    group_id: str,
    root: str | Path | None = None,
    status: str = "pending",
) -> dict[str, Any] | None:
    """Find a coalesced inbox group by group id or source inbox id."""

    wanted = str(group_id or "").strip()
    if not wanted:
        return None
    for group in list_inbox_groups(root=root, status=status, limit=200):
        inbox_ids = [str(item) for item in group.get("inbox_ids", [])]
        if wanted == str(group.get("group_id") or "") or wanted in inbox_ids:
            return group
    return None


def _inbox_paths(root: str | Path | None = None) -> list[Path]:
    """Find inbox artifacts under ``memory/*/*/*/inbox.jsonl``."""
    base = _base(root) / "memory"
    if not base.exists():
        return []
    return sorted(base.glob("*/*/*/inbox.jsonl"))


def update_inbox_items(
    inbox_ids: list[str],
    updates: Mapping[str, Any],
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Update matching inbox records across JSONL artifacts."""

    wanted = {str(item) for item in inbox_ids if str(item).strip()}
    if not wanted:
        raise ValueError("inbox_ids cannot be empty")

    updated_items: list[dict[str, Any]] = []
    for path in _inbox_paths(root):
        changed = False
        rewritten: list[dict[str, Any] | str] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    rewritten.append(line.rstrip("\n"))
                    continue
                if not isinstance(payload, dict):
                    rewritten.append(line.rstrip("\n"))
                    continue
                if str(payload.get("inbox_id") or "") in wanted:
                    payload.update(dict(updates))
                    payload["_artifact"] = str(path)
                    updated_items.append(payload)
                    payload = {k: v for k, v in payload.items() if k != "_artifact"}
                    changed = True
                rewritten.append(payload)
        if changed:
            with path.open("w", encoding="utf-8") as handle:
                for item in rewritten:
                    if isinstance(item, str):
                        handle.write(item + "\n")
                    else:
                        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    if not updated_items:
        raise ValueError("no matching inbox items found")
    return updated_items


async def promote_inbox_group(
    group_id: str,
    canonical_writer: CanonicalWriter,
    root: str | Path | None = None,
    key: str = "",
    value: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Promote an inbox group through an injected canonical writer."""

    group = find_inbox_group(group_id, root=root, status="pending")
    if group is None:
        raise ValueError(f"inbox group not found: {group_id}")

    canonical_key = str(key or group.get("key") or "").strip()
    canonical_value = str(value or group.get("value") or "").strip()
    if not canonical_key:
        raise ValueError("canonical key cannot be empty")
    if not canonical_value:
        raise ValueError("canonical value cannot be empty")

    result = await canonical_writer(canonical_key, canonical_value)
    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    inbox_ids = [str(item) for item in group.get("inbox_ids", [])]
    group_key = str(group.get("group_id", ""))
    relation_hints = _inbox_relation_hints(
        inbox_ids,
        target_id=_memory_target_id(canonical_key),
        relation_type="PROMOTED_TO",
        group_id=group_key,
    )
    updated = update_inbox_items(
        inbox_ids,
        {
            "status": "promoted",
            "reviewed_at": ts,
            "promoted_key": canonical_key,
            "promoted_value": canonical_value,
            "promotion_result": str(result),
        },
        root=root,
    )
    decision = append_curation_decision(
        {
            "kind": "memory_inbox",
            "action": "promote",
            "group_id": group_key,
            "inbox_ids": inbox_ids,
            "key": canonical_key,
            "value": canonical_value,
            "target_id": _memory_target_id(canonical_key),
            "relation_hints": relation_hints,
            "reinforcement_count": group.get("reinforcement_count", 1),
            "updated_count": len(updated),
            "writer_result": str(result),
        },
        root=root,
        timestamp=ts,
    )
    return {
        "group_id": group_key,
        "status": "promoted",
        "key": canonical_key,
        "value": canonical_value,
        "target_id": _memory_target_id(canonical_key),
        "relation_hints": relation_hints,
        "preview_command": "curator_workbench action=preview_hints",
        "materialize_command": "curator_workbench action=materialize_hints",
        "verify_graph_command": f"curator_workbench action=graph memory_key={canonical_key}",
        "reinforcement_count": group.get("reinforcement_count", 1),
        "inbox_ids": inbox_ids,
        "updated_count": len(updated),
        "writer_result": result,
        "decision_event": decision,
    }


def reject_inbox_group(
    group_id: str,
    reason: str,
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Reject an inbox group and mark all source records."""

    group = find_inbox_group(group_id, root=root, status="pending")
    if group is None:
        raise ValueError(f"inbox group not found: {group_id}")
    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    inbox_ids = [str(item) for item in group.get("inbox_ids", [])]
    updated = update_inbox_items(
        inbox_ids,
        {
            "status": "rejected",
            "reviewed_at": ts,
            "review_reason": reason,
        },
        root=root,
    )
    decision = append_curation_decision(
        {
            "kind": "memory_inbox",
            "action": "reject",
            "group_id": group.get("group_id", ""),
            "inbox_ids": inbox_ids,
            "key": group.get("key", ""),
            "value": group.get("value", ""),
            "reason": reason,
            "reinforcement_count": group.get("reinforcement_count", 1),
            "updated_count": len(updated),
        },
        root=root,
        timestamp=ts,
    )
    return {
        "group_id": group.get("group_id", ""),
        "status": "rejected",
        "reason": reason,
        "reinforcement_count": group.get("reinforcement_count", 1),
        "inbox_ids": inbox_ids,
        "updated_count": len(updated),
        "decision_event": decision,
    }
