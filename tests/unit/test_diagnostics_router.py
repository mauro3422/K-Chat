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

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/diagnostics?key_pattern=user:*")
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
    fake_bridge.request_peer_states.assert_awaited_once()
    fake_bridge.request_peer_memory_snapshots.assert_awaited_once_with(key_pattern="user:*")
    app.state.manage_memory_run.assert_awaited_once()
    assert app.state.manage_memory_run.await_args.kwargs["key_pattern"] == "user:*"


@pytest.mark.anyio
async def test_api_diagnostics_normalizes_string_peer_urls():
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
    fake_bridge.peer_urls = "  http://peer-a:8000/  "
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
                "queue_size": 0,
                "memory": {"revision": 12, "sync": 12, "is_fresh": True},
                "compare_summary": {"severity": "clean", "actions": [], "counts": {}, "has_conflicts": False},
            }
        ],
        "errors": [],
    })
    fake_bridge.request_peer_state = AsyncMock(return_value={
        "ok": True,
        "peer": "http://peer-a:8000",
        "state": {"node_id": "peer-a"},
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
    app.state.manage_memory_run = AsyncMock(return_value='{"only_in_md": [], "only_in_db": [], "mismatched": [], "rename_candidates": []}')

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/diagnostics?key_pattern=user:*")
    assert response.status_code == 200
    body = response.json()
    assert body["bridge"]["peer_urls"] == ["http://peer-a:8000"]
    assert body["cluster"]["peer_count"] == 1
    assert body["peer_memory"]["summary"]["configured_peer_count"] == 1
    assert body["peer_memory"]["summary"]["peer_count"] == 1

    peer_response = client.get("/api/diagnostics/peer?peer_url=http://peer-a:8000&kind=state")
    assert peer_response.status_code == 200
    assert peer_response.json()["state"]["node_id"] == "peer-a"


@pytest.mark.anyio
async def test_api_diagnostics_survives_failed_coordinator_snapshot():
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

    class _BrokenCoordinator:
        role = "primary"

        def snapshot(self):
            raise RuntimeError("snapshot failed")

        async def is_primary(self):
            return False

    class _Queue:
        persistence_path = "memory.db"

        def __len__(self):
            return 0

        def snapshot(self):
            return []

    class _LeaseManager:
        def snapshot(self):
            return None

    fake_bridge = MagicMock()
    fake_bridge.base_url = "http://127.0.0.1:8000"
    fake_bridge.peer_urls = []

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()

    app.state.node_coordinator = _BrokenCoordinator()
    app.state.node_bridge = fake_bridge
    app.state.memory_write_queue = _Queue()
    app.state.memory_lease_manager = _LeaseManager()
    app.state.manage_memory_run = AsyncMock(return_value='{"only_in_md":[],"only_in_db":[],"mismatched":[],"rename_candidates":[]}')

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/diagnostics?key_pattern=user:*")

    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["node"]["node_id"] == "node-a"
    assert body["node"]["role"] == "primary"
    assert body["memory"]["source"]["node_id"] == "node-a"


@pytest.mark.anyio
async def test_api_diagnostics_records_peer_snapshot_errors():
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
    fake_bridge.peer_urls = ["http://peer-a:8000", "http://peer-b:8000"]
    fake_bridge.broadcast_once = AsyncMock(return_value={"ok": True})
    fake_bridge.request_peer_states = AsyncMock(side_effect=RuntimeError("state request failed"))
    fake_bridge.request_peer_memory_snapshots = AsyncMock(side_effect=RuntimeError("memory request failed"))

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
    app.state.manage_memory_run = AsyncMock(return_value='{"only_in_md": [], "only_in_db": [], "mismatched": [], "rename_candidates": []}')

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/diagnostics?key_pattern=user:*")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["cluster"]["peer_count"] == 2
    assert body["cluster"]["reachable_peers"] == 0
    assert body["cluster"]["unreachable_peers"] == 2
    assert body["cluster"]["errors"][0]["source"] == "request_peer_states"
    assert body["peer_memory"]["summary"]["configured_peer_count"] == 2
    assert body["peer_memory"]["summary"]["peer_count"] == 0
    assert body["peer_memory"]["summary"]["error_count"] == 1
    assert body["peer_memory"]["errors"][0]["source"] == "request_peer_memory_snapshots"


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
    app.state.manage_memory_run = AsyncMock(return_value='{"only_in_md": [], "only_in_db": [], "mismatched": [], "rename_candidates": []}')

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/diagnostics?key_pattern=user:*")
    assert response.status_code == 200
    html = response.text
    assert "Filtro: user:*" in html
    assert 'const initialKeyPattern = "user:*";' in html
    assert "fetch(withKeyPattern('/api/diagnostics')" in html
    assert "withKeyPattern(`/api/diagnostics/peer?" in html
    assert "key_pattern: keyPattern" in html
    assert "Peers consultados:" in html
    assert 'data-peer-url="http://peer-a:8000"' in html
    assert 'data-peer-kind="diagnostics"' in html
    assert 'data-peer-kind="memory"' in html
    app.state.manage_memory_run.assert_awaited_once()
    assert app.state.manage_memory_run.await_args.kwargs["key_pattern"] == "user:*"


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

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/diagnostics/peer?peer_url=http://peer-a:8000&kind=diagnostics&key_pattern=user:*")
    assert response.status_code == 200
    body = response.json()
    assert body["peer"] == "http://peer-a:8000"
    assert body["snapshot"]["ok"] is True
    fake_bridge.request_peer_diagnostics.assert_awaited_once_with(peer="http://peer-a:8000", key_pattern="user:*")

    memory_response = client.get("/api/diagnostics/peer?peer_url=http://peer-a:8000&kind=memory&key_pattern=user:*")
    assert memory_response.status_code == 200
    fake_bridge.request_memory_snapshot.assert_awaited_once_with(key_pattern="user:*", peer="http://peer-a:8000")

    state_response = client.get("/api/diagnostics/peer?peer_url=http://peer-a:8000&kind=state&key_pattern=user:*")
    assert state_response.status_code == 200
    assert state_response.json()["state"]["node_id"] == "peer-a"
