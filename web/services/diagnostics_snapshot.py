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
    }
    if bridge is not None and bridge.peer_urls:
        try:
            memory_result = await bridge.request_peer_memory_snapshots(key_pattern=key_pattern)
            peer_memory = {
                "peers": [snapshot for snapshot in memory_result.get("snapshots", []) if isinstance(snapshot, dict)],
                "errors": [error for error in memory_result.get("errors", []) if isinstance(error, dict)],
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
