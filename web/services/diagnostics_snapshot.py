"""Shared helpers to assemble a unified diagnostics snapshot."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from src.coordination.lan_bridge import NodeLanBridge
from src.coordination.node_state import get_node_coordinator
from web.routers._memory_snapshot import build_memory_snapshot
from web.services.health_snapshot import (
    build_health_checks,
    build_health_coordination,
    build_health_runtime,
    checks_are_healthy,
)


def _get_coordinator(request: Request):
    return getattr(request.app.state, "node_coordinator", None) or get_node_coordinator(getattr(request.app.state, "config", None))


def _get_bridge(request: Request):
    bridge = getattr(request.app.state, "node_bridge", None)
    if bridge is not None:
        return bridge
    coordinator = _get_coordinator(request)
    cfg = getattr(request.app.state, "config", None)
    if coordinator is None:
        return None
    bridge = NodeLanBridge(config=cfg, coordinator=coordinator)
    request.app.state.node_bridge = bridge
    return bridge


def _snapshot_error(source: str, exc: Exception) -> dict[str, str]:
    return {"source": source, "error": str(exc)}


async def build_diagnostics_snapshot(request: Request, *, key_pattern: str = "") -> dict[str, Any]:
    coordinator = _get_coordinator(request)
    bridge = _get_bridge(request)
    cfg = getattr(request.app.state, "config", None)
    testing = bool(getattr(cfg, "testing", False))

    memory = await build_memory_snapshot(request, key_pattern=key_pattern)
    checks = await build_health_checks(cfg, testing=testing)

    peer_urls = list(bridge.peer_urls) if bridge is not None else []
    cluster = {
        "peer_count": len(peer_urls),
        "reachable_peers": 0,
        "unreachable_peers": len(peer_urls),
        "states": [],
        "errors": [],
    }
    if bridge is not None and peer_urls:
        try:
            peer_result = await bridge.request_peer_states()
            cluster = {
                "peer_count": len(peer_urls),
                "reachable_peers": len([state for state in peer_result.get("states", []) if isinstance(state, dict)]),
                "unreachable_peers": len([error for error in peer_result.get("errors", []) if isinstance(error, dict)]),
                "states": [state for state in peer_result.get("states", []) if isinstance(state, dict)],
                "errors": [error for error in peer_result.get("errors", []) if isinstance(error, dict)],
            }
        except Exception as exc:
            cluster = {
                "peer_count": len(peer_urls),
                "reachable_peers": 0,
                "unreachable_peers": len(peer_urls),
                "states": [],
                "errors": [_snapshot_error("request_peer_states", exc)],
            }

    peer_memory = {
        "peers": [],
        "errors": [],
        "summary": {
            "peer_count": 0,
            "configured_peer_count": len(peer_urls),
            "error_count": 0,
            "aligned_peers": 0,
            "stale_peers": 0,
            "stale_details": [],
            "peer_diffs": [],
        },
    }
    if bridge is not None and peer_urls:
        try:
            memory_result = await bridge.request_peer_memory_snapshots(key_pattern=key_pattern)
            local_revision = float(
                (((memory.get("memory") or {}).get("revision")) or 0.0)
                or (((memory.get("sync") or {}).get("last_memory_revision")) or 0.0)
            )
            stale_details: list[dict[str, Any]] = []
            peer_diffs: list[dict[str, Any]] = []
            aligned = 0
            stale = 0
            peers = [snapshot for snapshot in memory_result.get("snapshots", []) if isinstance(snapshot, dict)]
            for peer in peers:
                peer_memory_state = peer.get("memory") if isinstance(peer.get("memory"), dict) else {}
                peer_revision = float(
                    (peer_memory_state.get("revision") or 0.0)
                    or (peer.get("sync", {}).get("last_memory_revision") if isinstance(peer.get("sync"), dict) else 0.0)
                )
                peer_fresh = bool(peer_memory_state.get("is_fresh", False))
                peer_queue = int(peer.get("queue_size", 0) or 0)
                is_aligned = peer_fresh and peer_revision >= local_revision and peer_queue == 0
                if is_aligned:
                    aligned += 1
                else:
                    stale += 1
                    reasons: list[str] = []
                    if peer_queue > 0:
                        reasons.append("queue_pending")
                    if not peer_fresh:
                        reasons.append("not_fresh")
                    if peer_revision < local_revision:
                        reasons.append("revision_behind")
                    peer_diffs.append({
                        "peer_url": peer.get("peer_url", ""),
                        "local_revision": local_revision,
                        "peer_revision": peer_revision,
                        "revision_delta": max(0.0, local_revision - peer_revision),
                        "queue_size": peer_queue,
                        "is_fresh": peer_fresh,
                        "stale_reason": "+".join(reasons) if reasons else "unknown",
                        "compare_severity": (peer.get("compare_summary", {}) or {}).get("severity", "clean"),
                        "compare_actions": list((peer.get("compare_summary", {}) or {}).get("actions", []) or []),
                    })
                    stale_details.append({
                        "peer_url": peer.get("peer_url", ""),
                        "revision_delta": max(0.0, local_revision - peer_revision),
                        "queue_size": peer_queue,
                        "is_fresh": peer_fresh,
                        "severity": (peer.get("compare_summary", {}) or {}).get("severity", "clean"),
                        "stale_reason": "+".join(reasons) if reasons else "unknown",
                    })
            peer_memory = {
                "peers": peers,
                "errors": [error for error in memory_result.get("errors", []) if isinstance(error, dict)],
                "summary": {
                    "peer_count": len(peers),
                    "configured_peer_count": len(peer_urls),
                    "error_count": len([error for error in memory_result.get("errors", []) if isinstance(error, dict)]),
                    "aligned_peers": aligned,
                    "stale_peers": stale,
                    "stale_details": stale_details,
                    "peer_diffs": peer_diffs,
                },
            }
        except Exception as exc:
            peer_memory = {
                "peers": [],
                "errors": [_snapshot_error("request_peer_memory_snapshots", exc)],
                "summary": {
                    "peer_count": 0,
                    "configured_peer_count": len(peer_urls),
                    "error_count": 1,
                    "aligned_peers": 0,
                    "stale_peers": 0,
                    "stale_details": [],
                    "peer_diffs": [],
                },
            }

    try:
        coord_snapshot = coordinator.snapshot()
    except Exception:
        coord_snapshot = None

    try:
        failover_state = getattr(request.app.state, "failover_state", None)
        sync, health_memory, failover = build_health_runtime(
            cfg=cfg,
            coordinator_snapshot=coord_snapshot,
            coordinator_role=getattr(coordinator, "role", ""),
            queue_size=int(memory.get("queue_size", 0) or 0),
            queue_pending=list(memory.get("queue", []) or []),
            lease_snapshot=memory.get("lease"),
            failover_snapshot=failover_state.snapshot() if failover_state is not None else None,
        )
        health = {
            "status": "ok" if checks_are_healthy(checks, testing=testing) else "degraded",
            "checks": checks,
            "coordination": build_health_coordination(cfg=cfg, coordinator_snapshot=coord_snapshot, cluster=cluster),
            "memory": health_memory,
            "sync": sync,
            "failover": failover,
        }
    except Exception:
        health = {
            "status": "degraded",
            "checks": checks,
            "coordination": build_health_coordination(cfg=cfg, coordinator_snapshot=None, cluster=None),
            "memory": {
                "queue_size": 0,
                "queue_pending": [],
                "lease": None,
                "freshness": {"last_revision": 0.0, "last_sync": 0.0, "is_fresh": True},
            },
            "sync": {
                "role": str(getattr(cfg, "node_role", "secondary")),
                "is_primary": False,
                "has_recent_primary": False,
                "memory_is_fresh": True,
                "last_memory_revision": 0.0,
                "last_memory_sync": 0.0,
            },
            "failover": {
                "required_misses": 2,
                "miss_count": 0,
                "last_check_at": 0.0,
                "last_primary_seen_at": 0.0,
                "last_promotion_at": 0.0,
                "last_action": "idle",
                "last_reason": "",
                "promoted_role": "",
                "should_promote": False,
            },
        }

    snapshot = coord_snapshot if coord_snapshot is not None else memory.get("source", {})
    return {
        "node": snapshot,
        "bridge": {
            "base_url": bridge.base_url if bridge is not None else "",
            "peer_urls": bridge.peer_urls if bridge is not None else [],
        },
        "cluster": cluster,
        "peer_memory": peer_memory,
        "memory": memory,
        "health": health,
    }
