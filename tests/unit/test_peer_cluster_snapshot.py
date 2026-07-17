import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.anyio
async def test_build_peer_cluster_snapshot_normalizes_peer_urls_and_filters_entries():
    from web.services.peer_cluster_snapshot import build_peer_cluster_snapshot, peer_urls_from_bridge

    bridge = MagicMock()
    bridge.peer_urls = "  http://peer-a:8000/  "
    bridge.request_peer_states = AsyncMock(return_value={
        "states": [{"node_id": "peer-a"}, "ignored"],
        "errors": [{"peer_url": "http://peer-a:8000", "error": "timeout"}, None],
    })

    assert peer_urls_from_bridge(bridge) == ["http://peer-a:8000"]

    snapshot = await build_peer_cluster_snapshot(bridge)

    assert snapshot["peer_count"] == 1
    assert snapshot["reachable_peers"] == 1
    assert snapshot["unreachable_peers"] == 1
    assert snapshot["states"] == [{"node_id": "peer-a"}]
    assert snapshot["errors"] == [{"peer_url": "http://peer-a:8000", "error": "timeout"}]


@pytest.mark.anyio
async def test_build_peer_cluster_snapshot_survives_peer_state_failure():
    from web.services.peer_cluster_snapshot import build_peer_cluster_snapshot

    bridge = MagicMock()
    bridge.peer_urls = ["http://peer-a:8000", "http://peer-b:8000"]
    bridge.request_peer_states = AsyncMock(side_effect=RuntimeError("peer state failed"))

    snapshot = await build_peer_cluster_snapshot(bridge)

    assert snapshot["peer_count"] == 2
    assert snapshot["reachable_peers"] == 0
    assert snapshot["unreachable_peers"] == 2
    assert snapshot["errors"][0]["source"] == "request_peer_states"
