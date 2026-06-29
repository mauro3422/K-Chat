"""Session directory helpers for local and federated session lists."""

from __future__ import annotations

from typing import Any


def _safe_text(value: Any, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def session_summary_from_row(
    row: tuple[Any, ...],
    *,
    node_id: str,
    node_role: str,
    cluster_name: str,
    node_platform: str = "",
    source_url: str = "",
    source_mode: str = "local",
) -> dict[str, Any]:
    sid = _safe_text(row[0])
    first = row[1] if len(row) > 1 else ""
    last = row[2] if len(row) > 2 else ""
    count = int(row[3] or 0) if len(row) > 3 and row[3] is not None else 0
    name_idx = 5 if len(row) > 5 and isinstance(row[5], str) else 4
    favorite_idx = 7 if len(row) > 7 else 6
    name = _safe_text(row[name_idx] if len(row) > name_idx else "", sid[:8])
    is_favorite = bool(row[favorite_idx]) if len(row) > favorite_idx else False

    return {
        "id": sid,
        "name": name,
        "count": count,
        "first_str": str(first)[:19] if first else "",
        "last_str": str(last)[:19] if last else "",
        "last_seen_at": str(last) if last else "",
        "is_favorite": is_favorite,
        "node_id": _safe_text(node_id, "local"),
        "node_role": _safe_text(node_role, "secondary"),
        "node_platform": _safe_text(node_platform).lower(),
        "cluster_name": _safe_text(cluster_name, "kairos"),
        "source_url": _safe_text(source_url),
        "source_mode": _safe_text(source_mode, "local"),
    }


def sort_sessions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(entry: dict[str, Any]) -> tuple[int, str, str, str]:
        favorite = 1 if entry.get("is_favorite") else 0
        last_seen = _safe_text(entry.get("last_seen_at"), _safe_text(entry.get("last_str")))
        node_id = _safe_text(entry.get("node_id"))
        sid = _safe_text(entry.get("id"))
        return (favorite, f"{last_seen}".lower(), node_id.lower(), sid.lower())

    return sorted(entries, key=_key, reverse=True)


def merge_session_entries(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        for entry in group:
            sid = _safe_text(entry.get("id"))
            node_id = _safe_text(entry.get("node_id"), "local")
            source_url = _safe_text(entry.get("source_url"))
            key = (sid, node_id, source_url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return sort_sessions(merged)
