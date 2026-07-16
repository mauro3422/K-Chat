"""Shared helpers for peer cluster snapshots."""

from __future__ import annotations

from typing import Any


def snapshot_error(source: str, exc: Exception) -> dict[str, str]:
    return {"source": source, "error": str(exc)}


def _peer_urls_from_bridge(bridge: Any) -> list[str]:
    peer_urls = getattr(bridge, "peer_urls", []) or []
    if isinstance(peer_urls, str):
        return [peer_urls] if peer_urls else []
    return list(peer_urls)


def _dict_entries(items: Any) -> list[dict[str, Any]]:
    return [item for item in (items or []) if isinstance(item, dict)]


async def build_peer_cluster_snapshot(bridge: Any) -> dict[str, Any]:
    peer_urls = _peer_urls_from_bridge(bridge)
    if bridge is None or not peer_urls:
        return {
            "peer_count": 0,
            "reachable_peers": 0,
            "unreachable_peers": 0,
            "states": [],
            "errors": [],
        }

    try:
        peer_result = await bridge.request_peer_states()
    except Exception as exc:
        return {
            "peer_count": len(peer_urls),
            "reachable_peers": 0,
            "unreachable_peers": len(peer_urls),
            "states": [],
            "errors": [snapshot_error("request_peer_states", exc)],
        }

    states = _dict_entries(peer_result.get("states", []))
    errors = _dict_entries(peer_result.get("errors", []))
    return {
        "peer_count": len(peer_urls),
        "reachable_peers": len(states),
        "unreachable_peers": len(errors),
        "states": states,
        "errors": errors,
    }
