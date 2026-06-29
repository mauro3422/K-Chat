"""Federated session directory reconciliation tests.

Verifies that ``merge_session_entries`` deduplicates by ``sid`` using
``origin_node_id`` as the canonical owner signal — fixing the "duplicate
/weird-named sessions" symptom in the sidebar when two peers federate
their session lists.
"""

from __future__ import annotations

from web.services.session_directory import merge_session_entries, sort_sessions


def _entry(
    sid: str,
    *,
    name: str = "",
    node_id: str = "local",
    origin_node_id: str = "",
    source_url: str = "",
    last_seen_at: str = "",
    is_favorite: bool = False,
) -> dict:
    return {
        "id": sid,
        "name": name,
        "count": 0,
        "first_str": "",
        "last_str": last_seen_at[:19] if last_seen_at else "",
        "last_seen_at": last_seen_at,
        "is_favorite": is_favorite,
        "node_id": node_id,
        "node_role": "secondary",
        "node_platform": "",
        "cluster_name": "kairos",
        "source_url": source_url,
        "source_mode": "peer" if source_url else "local",
        "origin_node_id": origin_node_id,
    }


def test_merge_dedup_keeps_one_per_sid():
    """Same session on two peers collapses to a single entry."""
    laptop = _entry("sess-1", name="Laptop chat", node_id="laptop", origin_node_id="laptop")
    pc = _entry("sess-1", name="Laptop chat", node_id="pc-grande", origin_node_id="laptop")
    merged = merge_session_entries([laptop], [pc])
    assert len(merged) == 1
    assert merged[0]["id"] == "sess-1"


def test_merge_prefers_entry_whose_node_id_matches_origin_node_id():
    """If one peer's node_id equals the session's origin_node_id, it wins.

    That entry is canonical: it represents the node where the session was
    created, so its name and favorite flag are the most authoritive copy.
    """
    laptop = _entry(
        "sess-2",
        name="Canonical name on laptop",
        node_id="laptop",
        origin_node_id="laptop",
        last_seen_at="2026-06-29T10:00:00",
    )
    pc = _entry(
        "sess-2",
        name="Stale name on pc",
        node_id="pc-grande",
        origin_node_id="laptop",
        last_seen_at="2026-06-29T11:00:00",  # newer but not canonical
    )
    merged = merge_session_entries([laptop], [pc])
    assert len(merged) == 1
    assert merged[0]["name"] == "Canonical name on laptop"
    assert merged[0]["node_id"] == "laptop"


def test_merge_falls_back_to_latest_activity_when_origin_unknown():
    """Legacy rows without ``origin_node_id`` fall back to last_seen_at tie-break."""
    a = _entry(
        "sess-3",
        name="Older entry",
        node_id="laptop",
        origin_node_id="",
        last_seen_at="2026-06-28T10:00:00",
    )
    b = _entry(
        "sess-3",
        name="Newer entry",
        node_id="pc-grande",
        origin_node_id="",
        last_seen_at="2026-06-29T10:00:00",
    )
    merged = merge_session_entries([a], [b])
    assert len(merged) == 1
    assert merged[0]["name"] == "Newer entry"


def test_merge_distinct_sids_keep_all():
    """Different session IDs never collapse — they're genuinely separate sessions."""
    a = _entry("sess-A", name="Chat A")
    b = _entry("sess-B", name="Chat B")
    merged = merge_session_entries([a], [b])
    assert len(merged) == 2
    sids = {e["id"] for e in merged}
    assert sids == {"sess-A", "sess-B"}


def test_merge_preserves_favorite_flag_from_canonical_owner():
    """Favorite flag reconciles from the canonical owner, not from a stale peer."""
    laptop = _entry(
        "sess-4",
        name="Real session",
        node_id="laptop",
        origin_node_id="laptop",
        is_favorite=True,
    )
    peer = _entry(
        "sess-4",
        name="Real session",
        node_id="pc-grande",
        origin_node_id="laptop",
        is_favorite=False,
    )
    merged = merge_session_entries([laptop], [peer])
    assert len(merged) == 1
    assert merged[0]["is_favorite"] is True
    assert merged[0]["node_id"] == "laptop"