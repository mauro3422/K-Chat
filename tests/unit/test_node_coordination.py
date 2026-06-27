import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.anyio
async def test_node_coordinator_tracks_primary_and_peers():
    from src.coordination.node_state import NodeCoordinator

    cfg = MagicMock(node_id="node-a", node_role="secondary", cluster_name="kairos", node_heartbeat_ttl=10.0)
    coordinator = NodeCoordinator(cfg)

    assert coordinator.node_id == "node-a"
    assert coordinator.role == "secondary"
    assert coordinator.cluster_name == "kairos"

    await coordinator.beat()
    await coordinator.record_peer_heartbeat("node-b", "primary", "http://192.168.1.20:8000")
    snapshot = coordinator.snapshot()

    assert snapshot["node_id"] == "node-a"
    assert snapshot["role"] == "secondary"
    assert snapshot["has_recent_primary"] is True
    assert len(snapshot["peers"]) == 1
    assert snapshot["peers"][0]["node_id"] == "node-b"

    await coordinator.promote()
    assert await coordinator.is_primary() is True


@pytest.mark.anyio
async def test_memory_freshness_requires_sync_at_or_after_revision():
    from src.coordination.node_state import NodeCoordinator

    coordinator = NodeCoordinator()
    assert coordinator.snapshot()["memory_is_fresh"] is True
    await coordinator.mark_memory_revision()
    assert coordinator.snapshot()["memory_is_fresh"] is False
    await coordinator.mark_memory_sync()
    assert coordinator.snapshot()["memory_is_fresh"] is True


@pytest.mark.anyio
async def test_node_router_exposes_state_and_heartbeat():
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

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            state_response = client.get("/api/node/state")
            assert state_response.status_code == 200
            state = state_response.json()
            assert state["node_id"] == "node-a"
            assert state["role"] == "primary"
            assert state["cluster_name"] == "kairos"

            hb_response = client.post(
                "/api/node/heartbeat",
                json={"node_id": "node-b", "role": "secondary", "base_url": "http://192.168.1.21:8000"},
            )
            assert hb_response.status_code == 200
            hb = hb_response.json()
            assert hb["ok"] is True
            assert hb["state"]["peers"][0]["node_id"] == "node-b"
            assert app.state.node_bridge.peer_urls == ["http://192.168.1.21:8000"]

            promote_response = client.post("/api/node/promote")
            assert promote_response.status_code == 200
            assert promote_response.json()["state"]["role"] == "primary"


@pytest.mark.anyio
async def test_node_router_receives_event_and_publishes_bus():
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
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/node/event",
                json={"type": "memory_updated", "data": {"session_id": "s1"}},
            )
            assert response.status_code == 200
            assert response.json()["type"] == "memory_updated"
            fake_bus.publish.assert_awaited_once()


@pytest.mark.anyio
async def test_node_router_exposes_local_session_directory():
    from web.routers.node import node_sessions

    fake_repos = MagicMock()
    fake_repos.sessions = AsyncMock()
    fake_repos.sessions.get_all.return_value = [
        ("sess-local", "2026-06-19T09:00:00", "2026-06-19T10:00:00", 2, "Local Session", None, 0),
    ]

    req = MagicMock()
    req.base_url = "http://127.0.0.1:8000/"
    req.app.state.repos = fake_repos
    req.app.state.node_coordinator = MagicMock(
        snapshot=lambda: {"node_id": "node-a", "role": "primary", "cluster_name": "kairos"},
        node_id="node-a",
        role="primary",
        cluster_name="kairos",
    )

    with patch("web.routers.node._request_repos", return_value=fake_repos):
        response = await node_sessions(req, limit=50)

    payload = response.body.decode()
    assert response.status_code == 200
    assert "sess-local" in payload
    assert "node-a" in payload


@pytest.mark.anyio
async def test_node_event_marks_memory_revision_on_memory_updated_via_lan():
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
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/node/event",
                json={"type": "memory_updated", "data": {"session_id": "s1"}, "source": {"node_id": "peer-a"}},
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert app.state.node_coordinator.snapshot()["last_memory_revision"] > 0


@pytest.mark.anyio
async def test_node_event_marks_memory_sync_on_memory_write_completed_via_lan():
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
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/node/event",
                json={"type": "memory_write_completed", "data": {"key": "Preferencia"}, "source": {"node_id": "peer-a"}},
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert app.state.node_coordinator.snapshot()["last_memory_sync"] > 0


@pytest.mark.anyio
async def test_node_event_marks_memory_revision_on_memory_updated():
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
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/events/notify",
                json={"type": "memory_updated", "data": {"session_id": "s1"}, "source": {"node_id": "peer-a"}},
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert app.state.node_coordinator.snapshot()["last_memory_revision"] > 0


@pytest.mark.anyio
async def test_node_notify_marks_memory_sync_on_memory_write_completed():
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
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/events/notify",
                json={"type": "memory_write_completed", "data": {"key": "Preferencia"}, "source": {"node_id": "peer-a"}},
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert app.state.node_coordinator.snapshot()["last_memory_sync"] > 0


@pytest.mark.anyio
async def test_node_memory_snapshot_primary_returns_local_memory_snapshot():
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
    compare_payload = {
        "only_in_md": ["Preferencia"],
        "only_in_db": [],
        "mismatched": [],
        "rename_candidates": [],
        "matched": 1,
        "md_total": 1,
        "db_total": 1,
    }

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.manage_memory_run = AsyncMock(return_value=json.dumps(compare_payload))
        app.state.event_bus = MagicMock()
        app.state.event_bus.publish = AsyncMock()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/memory/snapshot?key_pattern=user:*")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["compare"]["only_in_md"] == ["Preferencia"]
            assert body["queue_path"]
            assert body["source"]["mode"] != "peer"


@pytest.mark.anyio
async def test_node_memory_snapshot_secondary_fetches_from_peer():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )
    fake_bridge = MagicMock()
    fake_bridge.peer_urls = ["http://peer-a:8000"]
    fake_bridge.request_memory_snapshot = AsyncMock(
        return_value={
            "ok": True,
            "peer": "http://peer-a:8000",
            "snapshot": {
                "ok": True,
                "lease": None,
                "queue_size": 0,
                "queue": [],
                "queue_path": "/tmp/peer-queue.json",
                "memory": {"revision": 1.0, "sync": 2.0, "is_fresh": True},
                "compare": {"only_in_md": [], "only_in_db": [], "mismatched": [], "rename_candidates": []},
            },
        }
    )

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
        app.state.event_bus = MagicMock()
        app.state.event_bus.publish = AsyncMock()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/memory/snapshot?key_pattern=user:*")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["queue_path"] == "/tmp/peer-queue.json"
            assert body["source"]["mode"] == "peer"
            fake_bridge.request_memory_snapshot.assert_awaited_once()


@pytest.mark.anyio
async def test_node_diagnostics_combines_node_bridge_and_memory_snapshot():
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
        peer_urls="",
    )
    compare_payload = {
        "only_in_md": ["Preferencia"],
        "only_in_db": [],
        "mismatched": [],
        "rename_candidates": [],
        "matched": 1,
        "md_total": 1,
        "db_total": 1,
    }

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.manage_memory_run = AsyncMock(return_value=json.dumps(compare_payload))
        app.state.event_bus = MagicMock()
        app.state.event_bus.publish = AsyncMock()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/diagnostics?key_pattern=user:*")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["node"]["node_id"] == "node-a"
            assert body["memory"]["ok"] is True


@pytest.mark.anyio
async def test_node_sync_status_reports_queue_and_memory_state():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.memory_write_queue.enqueue("Preferencia", "Python", source_node="node-b", reason="primary_unavailable")
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/sync/status")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["node"]["role"] == "secondary"
            assert body["bridge"]["peer_urls"] == []
            assert body["cluster"]["peer_count"] == 0
            assert body["queue"]["size"] == 1
            assert body["queue"]["pending"][0]["key"] == "Preferencia"
            assert body["sync"]["is_primary"] is False


@pytest.mark.anyio
async def test_node_sync_status_includes_peer_states():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )

    fake_bridge = MagicMock()
    fake_bridge.base_url = "http://127.0.0.1:8000"
    fake_bridge.peer_urls = ["http://peer-a:8000"]
    fake_bridge.request_peer_states = AsyncMock(return_value={
        "ok": True,
        "peers": ["http://peer-a:8000"],
        "states": [
            {
                "node_id": "peer-a",
                "role": "primary",
                "healthy": True,
                "memory_is_fresh": True,
                "peer_url": "http://peer-a:8000",
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
            response = client.get("/api/node/sync/status")
            assert response.status_code == 200
            body = response.json()
            assert body["cluster"]["peer_count"] == 1
            assert body["cluster"]["reachable_peers"] == 1
            assert body["cluster"]["states"][0]["node_id"] == "peer-a"
            assert body["cluster"]["states"][0]["healthy"] is True


@pytest.mark.anyio
async def test_node_runtime_reports_normal_primary_state():
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
        peer_urls="",
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/runtime")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["mode"] == "normal"
            assert body["memory"]["write"]["can_write"] is True
            assert body["memory"]["write"]["mode"] == "local_primary"


@pytest.mark.anyio
async def test_node_runtime_reports_fallback_when_secondary_lost_primary():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
        peer_urls="",
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/runtime")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is False
            assert body["mode"] == "fallback"
            assert "primary_not_recent" in body["reasons"]
            assert body["memory"]["write"]["mode"] == "queue_until_primary"


@pytest.mark.anyio
async def test_node_runtime_reports_degraded_when_memory_is_not_fresh():
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
        peer_urls="",
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        await app.state.node_coordinator.mark_memory_revision({"test": "dirty_memory"})
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/runtime")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is False
            assert body["mode"] == "degraded"
            assert "memory_not_fresh" in body["reasons"]
            assert body["memory"]["is_fresh"] is False


@pytest.mark.anyio
async def test_node_memory_request_primary_applies_write():
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
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        app.state.save_memory_run = AsyncMock(return_value="[OK] memory write approved by primary.")
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/node/memory/request",
                json={"key": "Preferencia", "value": "Python", "source": {"node_id": "node-b"}},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["granted"] is True
            app.state.save_memory_run.assert_awaited_once()
            assert fake_bus.publish.await_count == 2
            assert app.state.node_coordinator.snapshot()["last_memory_revision"] > 0


@pytest.mark.anyio
async def test_node_memory_request_secondary_queues_when_not_primary():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/node/memory/request",
                json={"key": "Preferencia", "value": "Python", "source": {"node_id": "node-b"}},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["queued"] is True
            queue_response = client.get("/api/node/memory/queue")
            assert queue_response.status_code == 200
            assert queue_response.json()["pending"][0]["key"] == "Preferencia"
            fake_bus.publish.assert_awaited_once()


@pytest.mark.anyio
async def test_node_promote_flushes_pending_memory_queue():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )
    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.event_bus = fake_bus
        app.state.save_memory_run = AsyncMock(return_value="[OK] memory write applied.")
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post(
                "/api/node/memory/request",
                json={"key": "Preferencia", "value": "Python", "source": {"node_id": "node-b"}},
            )

            with patch("web.routers.node.log_event") as mock_log:
                promote_response = client.post("/api/node/promote")
            assert promote_response.status_code == 200
            assert promote_response.json()["applied"][0]["key"] == "Preferencia"
            app.state.save_memory_run.assert_awaited_once()
            assert fake_bus.publish.await_count >= 2
            assert app.state.node_coordinator.snapshot()["last_memory_sync"] > 0
            mock_log.assert_called_once()

            queue_response = client.get("/api/node/memory/queue")
            assert queue_response.status_code == 200
            assert queue_response.json()["pending"] == []


@pytest.mark.anyio
async def test_node_promote_recovers_persisted_memory_queue_after_restart(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from web.app_factory import create_app
    from src.coordination.memory_write_queue import reset_memory_write_queue

    queue_path = tmp_path / "memory_write_queue.json"
    monkeypatch.setenv("KAIROS_MEMORY_WRITE_QUEUE_PATH", str(queue_path))

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app1 = create_app()

    app1.state.memory_write_queue.enqueue("Preferencia", "Python", source_node="node-b", reason="primary_unavailable")
    assert queue_path.exists()
    reset_memory_write_queue()

    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app2 = create_app()
        app2.state.event_bus = fake_bus
        app2.state.save_memory_run = AsyncMock(return_value="[OK] memory write applied.")
        with TestClient(app2, raise_server_exceptions=False) as client:
            response = client.post("/api/node/promote")
            assert response.status_code == 200
            body = response.json()
            assert body["applied"][0]["key"] == "Preferencia"
            app2.state.save_memory_run.assert_awaited_once()
            assert app2.state.memory_write_queue.snapshot() == []
            assert queue_path.exists()


@pytest.mark.anyio
async def test_primary_startup_autoflushes_persisted_memory_queue(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    queue_path = tmp_path / "memory_write_queue.json"
    monkeypatch.setenv("KAIROS_MEMORY_WRITE_QUEUE_PATH", str(queue_path))

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="primary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.memory_write_queue.enqueue("Preferencia", "Python", source_node="node-b", reason="primary_unavailable")
        app.state.save_memory_run = AsyncMock(return_value="[OK] memory write applied.")
        app.state.event_bus = MagicMock()
        app.state.event_bus.publish = AsyncMock()
        with TestClient(app, raise_server_exceptions=False):
            pass

        app.state.save_memory_run.assert_awaited_once()
        assert app.state.memory_write_queue.snapshot() == []
        assert app.state.node_coordinator.snapshot()["last_memory_sync"] > 0


@pytest.mark.anyio
async def test_node_promote_rejects_when_leader_lease_is_busy():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        app.state.leader_lease_manager.acquire("other-node", ttl=30.0, reason="busy")
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/api/node/promote")
            assert response.status_code == 409
            assert response.json()["error"] == "leader lease busy"


@pytest.mark.anyio
async def test_secondary_auto_promotes_when_primary_is_missing():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        peer_urls="http://peer-a:8000",
        node_heartbeat_ttl=0.2,
        node_failover_check_interval=0.05,
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
        patch("src.coordination.lan_bridge.NodeLanBridge.broadcast_once", new_callable=AsyncMock, return_value={"ok": True}),
    ):
        app = create_app()
        app.state.event_bus = MagicMock()
        app.state.event_bus.publish = AsyncMock()
        app.state.node_bridge = MagicMock()
        app.state.node_bridge.broadcast_once = AsyncMock(return_value={"ok": True})
        with TestClient(app, raise_server_exceptions=False):
            import anyio
            import time

            deadline = time.time() + 2.0
            while time.time() < deadline:
                if app.state.node_coordinator.role == "primary":
                    break
                await anyio.sleep(0.05)

            assert app.state.node_coordinator.role == "primary"


@pytest.mark.anyio
async def test_node_failover_status_reports_state():
    from fastapi.testclient import TestClient
    from web.app_factory import create_app

    fake_config = MagicMock(
        testing=True,
        log_level="INFO",
        http_rate_limit=10,
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=0.2,
        node_failover_check_interval=0.05,
        node_failover_required_misses=2,
    )

    with (
        patch("web.app_factory.load_config", return_value=fake_config),
        patch("web.app_factory.init_db", new_callable=AsyncMock),
        patch("web.app_factory.init_memory_db", new_callable=AsyncMock),
        patch("web.app_factory.get_repos", return_value=MagicMock()),
        patch("web.app_factory.deps.searxng_start", return_value=None),
        patch("web.app_factory.deps.searxng_stop", return_value=None),
    ):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/node/failover/status")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["required_misses"] == 2
            assert body["miss_count"] == 0
            assert body["should_promote"] is False
            assert body["node"]["node_id"] == "node-a"
