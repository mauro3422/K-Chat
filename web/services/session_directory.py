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
    # origin_node_id was added in migration 025. When present (row length > 8),
    # it tells us which node created this session — the federated merge uses
    # it to pick which entry is canonical when the same sid appears in
    # multiple peers' directories.
    origin_node_id = _safe_text(row[8]) if len(row) > 8 else ""

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
        "origin_node_id": origin_node_id,
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
    """Reconcile session directory entries from multiple nodes.

    Dedup key is ``sid`` (the session UUID). When the same sid shows up in
    more than one peer's directory, we keep ONE entry:

      1. If exactly one entry's ``node_id`` matches its own ``origin_node_id``
         (i.e. the entry is on the node that *created* the session), that
         entry wins — its name, favorite flag, and source_url are the
         canonical truth.
      2. Otherwise (origin unknown on any side, or origin points at a third
         node that's not in this merge), keep the entry with the latest
         ``last_seen_at`` activity timestamp.

    Combined with the existing ``origin_node_id`` column (migration 025),
    this makes the federated sidebar show one row per session even when
    two peers report it — which fixes the "duplicate / weird-named sessions"
    symptom Mauro reported.
    """
    by_sid: dict[str, list[dict[str, Any]]] = {}
    for group in groups:
        for entry in group:
            sid = _safe_text(entry.get("id"))
            if not sid:
                continue
            by_sid.setdefault(sid, []).append(entry)

    merged: list[dict[str, Any]] = []
    for sid, entries in by_sid.items():
        if len(entries) == 1:
            merged.append(entries[0])
            continue

        # Multiple entries for the same sid → pick the canonical one.
        # Priority 1: an entry whose node_id matches its own origin_node_id.
        canonical = None
        for entry in entries:
            if _safe_text(entry.get("origin_node_id")) and \
               _safe_text(entry.get("origin_node_id")) == _safe_text(entry.get("node_id")):
                canonical = entry
                break

        if canonical is None:
            # Priority 2: latest last_seen_at (proxy for freshest state).
            canonical = max(
                entries,
                key=lambda e: _safe_text(e.get("last_seen_at"), _safe_text(e.get("last_str"))),
            )

        merged.append(canonical)

    return sort_sessions(merged)
