"""Node observability helpers — pure business logic for runtime/memory reporting.

These functions analyze coordinator snapshots, memory queues, and leader leases
to compute the runtime mode, write mode, and observability metrics exposed by
the node runtime/sync-status endpoints.

Lives in ``web/services/`` (not ``web/routers/``) because it is pure domain
logic — no FastAPI imports, no ``Request`` objects. Callers pass plain values
(snapshot dicts, queue objects, lease objects, timestamps).
"""

from __future__ import annotations


def _runtime_mode(
    snapshot: dict,
    cluster: dict,
    queue_size: int,
    failover: dict,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    role = str(snapshot.get("role", "secondary"))
    healthy = snapshot.get("healthy") is True
    has_recent_primary = snapshot.get("has_recent_primary") is True
    memory_is_fresh = snapshot.get("memory_is_fresh") is True
    peer_count = int(cluster.get("peer_count", 0) or 0)
    reachable_peers = int(cluster.get("reachable_peers", 0) or 0)

    if not healthy:
        reasons.append("local_heartbeat_stale")
    if not memory_is_fresh:
        reasons.append("memory_not_fresh")
    if queue_size > 0:
        reasons.append("memory_queue_pending")
    if peer_count > 0 and reachable_peers == 0:
        reasons.append("configured_peers_unreachable")
    if failover.get("should_promote") is True:
        reasons.append("failover_should_promote")
    if role == "secondary" and not has_recent_primary:
        reasons.append("primary_not_recent")

    fallback_reasons = {"failover_should_promote", "primary_not_recent"}
    if any(reason in fallback_reasons for reason in reasons):
        return "fallback", reasons
    if reasons:
        return "degraded", reasons
    return "normal", ["healthy"]


def _memory_write_mode(snapshot: dict, mode: str) -> dict:
    role = str(snapshot.get("role", "secondary"))
    preferred_role = str(snapshot.get("preferred_role", "secondary"))
    has_recent_primary = snapshot.get("has_recent_primary") is True
    if role == "primary" and preferred_role != "primary":
        return {"can_write": True, "mode": "temporary_primary_replay", "target": "local_then_peer_primary"}
    if role == "primary":
        return {"can_write": True, "mode": "local_primary", "target": "local"}
    if has_recent_primary:
        return {"can_write": False, "mode": "delegate_to_primary", "target": "peer_primary"}
    if mode == "fallback":
        return {"can_write": False, "mode": "queue_until_primary", "target": "local_queue"}
    return {"can_write": False, "mode": "read_only_secondary", "target": "none"}


def _age_seconds(timestamp: float, now: float) -> float | None:
    if timestamp <= 0:
        return None
    return max(0.0, round(now - timestamp, 3))


def _lease_observability(lease, now: float) -> dict:
    if lease is None:
        return {"active": False, "owner_node_id": "", "reason": "", "expires_in_seconds": None}
    lease_data = lease.to_dict()
    expires_at = float(lease_data.get("expires_at", 0.0) or 0.0)
    return {
        "active": expires_at > now,
        "owner_node_id": str(lease_data.get("owner_node_id", "")),
        "reason": str(lease_data.get("reason", "")),
        "expires_in_seconds": round(expires_at - now, 3) if expires_at else None,
    }


def _memory_observability(snapshot: dict, queue, lease, now: float) -> dict:
    revision = float(snapshot.get("last_memory_revision", 0.0) or 0.0)
    sync = float(snapshot.get("last_memory_sync", 0.0) or 0.0)
    pending = queue.snapshot()
    return {
        "revision_age_seconds": _age_seconds(revision, now),
        "sync_age_seconds": _age_seconds(sync, now),
        "sync_lag_seconds": round(sync - revision, 3) if revision or sync else 0.0,
        "queue_size": len(queue),
        "queue_oldest_age_seconds": _age_seconds(float(pending[0].get("requested_at", 0.0) or 0.0), now) if pending else None,
        "queue_reasons": sorted({str(item.get("reason", "")) for item in pending if isinstance(item, dict) and item.get("reason")}),
        "lease": _lease_observability(lease, now),
    }