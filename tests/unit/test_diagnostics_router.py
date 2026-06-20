import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.anyio
async def test_api_diagnostics_returns_unified_snapshot():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="primary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )
    fake_bridge = MagicMock()
    fake_bridge.base_url = "http://127.0.0.1:8000"
    fake_bridge.peer_urls = ["http://peer-a:8000"]
    fake_bridge.broadcast_once = AsyncMock(return_value={"ok": True})
    fake_bridge.request_peer_states = AsyncMock(return_value={
        "ok": True,
        "peers": ["http://peer-a:8000"],
        "states": [
            {
                "node_id": "peer-a",
                "role": "secondary",
                "healthy": True,
                "memory_is_fresh": True,
                "peer_url": "http://peer-a:8000",
            }
        ],
        "errors": [],
    })
    fake_bridge.request_peer_memory_snapshots = AsyncMock(return_value={
        "ok": True,
        "peers": ["http://peer-a:8000"],
        "snapshots": [
            {
                "peer_url": "http://peer-a:8000",
                "queue_size": 1,
                "memory": {"revision": 12, "sync": 12, "is_fresh": False},
                "compare_summary": {"severity": "medium", "actions": ["revisar"], "counts": {}, "has_conflicts": True},
            }
        ],
        "errors": [],
    })

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()

    app.state.node_bridge = fake_bridge
    app.state.manage_memory_run = AsyncMock(return_value='{"compare_summary": {"severity": "clean", "actions": [], "counts": {}, "has_conflicts": false}, "queue_size": 0, "queue_path": "", "memory": {"revision": 0, "sync": 0, "is_fresh": true}, "compare": {}}')

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/diagnostics")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["node"]["node_id"] == "node-a"
        assert body["bridge"]["base_url"] == "http://127.0.0.1:8000"
        assert body["peer_memory"]["peers"][0]["peer_url"] == "http://peer-a:8000"
        assert body["peer_memory"]["summary"]["peer_count"] == 1
        assert body["peer_memory"]["summary"]["stale_peers"] == 1
        assert body["peer_memory"]["summary"]["stale_details"][0]["stale_reason"] == "queue_pending+not_fresh"
        assert body["peer_memory"]["summary"]["peer_diffs"][0]["compare_severity"] == "medium"
        assert "memory" in body
        assert "health" in body


@pytest.mark.anyio
async def test_diagnostics_page_contains_peer_action_links():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="primary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )
    fake_bridge = MagicMock()
    fake_bridge.base_url = "http://127.0.0.1:8000"
    fake_bridge.peer_urls = ["http://peer-a:8000"]
    fake_bridge.broadcast_once = AsyncMock(return_value={"ok": True})
    fake_bridge.request_peer_states = AsyncMock(return_value={
        "ok": True,
        "peers": ["http://peer-a:8000"],
        "states": [
            {
                "node_id": "peer-a",
                "role": "secondary",
                "healthy": True,
                "memory_is_fresh": True,
                "peer_url": "http://peer-a:8000",
            }
        ],
        "errors": [],
    })
    fake_bridge.request_peer_memory_snapshots = AsyncMock(return_value={
        "ok": True,
        "peers": ["http://peer-a:8000"],
        "snapshots": [
            {
                "peer_url": "http://peer-a:8000",
                "queue_size": 1,
                "memory": {"revision": 12, "sync": 12, "is_fresh": False},
                "compare_summary": {"severity": "medium", "actions": ["revisar"], "counts": {}, "has_conflicts": True},
            }
        ],
        "errors": [],
    })

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()

    app.state.node_bridge = fake_bridge

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/diagnostics")
        assert response.status_code == 200
        html = response.text
        assert 'data-peer-url="http://peer-a:8000"' in html
        assert 'data-peer-kind="diagnostics"' in html
        assert 'data-peer-kind="memory"' in html


@pytest.mark.anyio
async def test_api_peer_diagnostics_proxies_allowed_peer():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="primary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )
    fake_bridge = MagicMock()
    fake_bridge.base_url = "http://127.0.0.1:8000"
    fake_bridge.peer_urls = ["http://peer-a:8000"]
    fake_bridge.broadcast_once = AsyncMock(return_value={"ok": True})
    fake_bridge.request_peer_diagnostics = AsyncMock(return_value={
        "ok": True,
        "peer": "http://peer-a:8000",
        "snapshot": {"ok": True, "memory": {"queue_size": 0}},
    })
    fake_bridge.request_peer_state = AsyncMock(return_value={
        "ok": True,
        "peer": "http://peer-a:8000",
        "state": {"node_id": "peer-a"},
    })
    fake_bridge.request_memory_snapshot = AsyncMock(return_value={
        "ok": True,
        "peer": "http://peer-a:8000",
        "snapshot": {"ok": True, "memory": {"queue_size": 0}},
    })

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()

    app.state.node_bridge = fake_bridge

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/diagnostics/peer?peer_url=http://peer-a:8000&kind=diagnostics")
        assert response.status_code == 200
        body = response.json()
        assert body["peer"] == "http://peer-a:8000"
        assert body["snapshot"]["ok"] is True

        state_response = client.get("/api/diagnostics/peer?peer_url=http://peer-a:8000&kind=state")
        assert state_response.status_code == 200
        assert state_response.json()["state"]["node_id"] == "peer-a"
