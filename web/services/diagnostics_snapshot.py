"""Shared helpers to assemble a unified diagnostics snapshot."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from src.coordination.lan_bridge import NodeLanBridge
from src.coordination.node_state import get_node_coordinator
from web.routers._memory_snapshot import build_memory_snapshot


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


async def build_diagnostics_snapshot(request: Request, *, key_pattern: str = "") -> dict[str, Any]:
    coordinator = _get_coordinator(request)
    bridge = _get_bridge(request)
    health = None
    try:
        from web.routers.health import health as health_endpoint

        health_resp = await health_endpoint(request)
        if hasattr(health_resp, "body"):
            health = json.loads(health_resp.body.decode("utf-8"))
    except Exception:
        health = None

    memory = await build_memory_snapshot(request, key_pattern=key_pattern)
    cluster = {
        "peer_count": 0,
        "reachable_peers": 0,
        "unreachable_peers": 0,
        "states": [],
        "errors": [],
    }
    if bridge is not None and bridge.peer_urls:
        try:
            peer_result = await bridge.request_peer_states()
            cluster = {
                "peer_count": len(bridge.peer_urls),
                "reachable_peers": len([state for state in peer_result.get("states", []) if isinstance(state, dict)]),
                "unreachable_peers": len([error for error in peer_result.get("errors", []) if isinstance(error, dict)]),
                "states": [state for state in peer_result.get("states", []) if isinstance(state, dict)],
                "errors": [error for error in peer_result.get("errors", []) if isinstance(error, dict)],
            }
        except Exception:
            pass

    peer_memory = {
        "peers": [],
        "errors": [],
        "summary": {
            "peer_count": 0,
            "aligned_peers": 0,
            "stale_peers": 0,
            "stale_details": [],
        },
    }
    if bridge is not None and bridge.peer_urls:
        try:
            memory_result = await bridge.request_peer_memory_snapshots(key_pattern=key_pattern)
            local_revision = float(
                (((memory.get("memory") or {}).get("revision")) or 0.0)
                or (((memory.get("sync") or {}).get("last_memory_revision")) or 0.0)
            )
            stale_details: list[dict[str, Any]] = []
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
                    "aligned_peers": aligned,
                    "stale_peers": stale,
                    "stale_details": stale_details,
                },
            }
        except Exception:
            pass

    snapshot = coordinator.snapshot()
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
