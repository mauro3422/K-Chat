import sqlite3
from collections import UserDict
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers.health import router


def _make_client(config):
    app = FastAPI()
    app.state.config = config
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_health_reports_database_ok(tmp_path):
    db_path = tmp_path / "sessions.db"
    sqlite3.connect(db_path).close()

    config = SimpleNamespace(
        testing=False,
        sessions_db_path=str(db_path),
        opencode_zen_api_key="",
        node_role="secondary",
        cluster_name="kairos",
    )

    with _make_client(config) as client:
        response = client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


def test_live_endpoint_is_minimal_and_fast(tmp_path):
    config = SimpleNamespace(
        testing=False,
        node_id="node-1",
        node_role="secondary",
    )

    with _make_client(config) as client:
        response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "node_id": "node-1",
        "role": "secondary",
    }


def test_health_marks_missing_database_degraded_when_not_testing(tmp_path):
    config = SimpleNamespace(
        testing=False,
        sessions_db_path=str(tmp_path / "missing.db"),
        opencode_zen_api_key="",
        node_role="secondary",
        cluster_name="kairos",
    )

    with _make_client(config) as client:
        response = client.get("/health")

    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "error"


def test_health_skips_missing_database_when_testing(tmp_path):
    config = SimpleNamespace(
        testing=True,
        sessions_db_path=str(tmp_path / "missing.db"),
        opencode_zen_api_key="",
        node_role="secondary",
        cluster_name="kairos",
    )

    with _make_client(config) as client:
        response = client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "skipped"


def test_health_reports_runtime_state_from_app_objects(tmp_path, monkeypatch):
    db_path = tmp_path / "sessions.db"
    sqlite3.connect(db_path).close()

    class _Coordinator:
        role = "primary"

        def snapshot(self):
            return UserDict(
                {
                    "node_id": "node-1",
                    "role": "primary",
                    "has_recent_primary": True,
                    "memory_is_fresh": False,
                    "last_memory_revision": 12.5,
                    "last_memory_sync": 13.75,
                    "peers": [{"node_id": "peer-a"}, {"node_id": "peer-b"}],
                }
            )

    class _Queue:
        def __len__(self):
            return 2

        def snapshot(self):
            return [{"id": "pending-1"}, {"id": "pending-2"}]

    class _LeaseManager:
        def snapshot(self):
            return UserDict(
                {
                    "owner_node_id": "node-1",
                    "acquired_at": 1.0,
                    "updated_at": 2.0,
                    "expires_at": 3.0,
                    "reason": "memory_write",
                }
            )

    class _FailoverState:
        def snapshot(self):
            return UserDict(
                {
                    "required_misses": 3,
                    "miss_count": 3,
                    "last_check_at": 4.0,
                    "last_primary_seen_at": 5.0,
                    "last_promotion_at": 6.0,
                    "last_action": "promoted",
                    "last_reason": "leader_election",
                    "promoted_role": "primary",
                    "should_promote": True,
                }
            )

    async def _fake_peer_cluster_state(request):
        return {
            "peer_count": 2,
            "reachable_peers": 1,
            "unreachable_peers": 1,
            "states": [{"node_id": "peer-a", "role": "secondary"}],
            "errors": [{"node_id": "peer-b", "error": "timeout"}],
        }

    monkeypatch.setattr("web.routers.health._peer_cluster_state", _fake_peer_cluster_state)

    config = SimpleNamespace(
        testing=False,
        sessions_db_path=str(db_path),
        opencode_zen_api_key="secret-key",
        node_role="primary",
        cluster_name="kairos",
        node_id="node-1",
    )

    app = FastAPI()
    app.state.config = config
    app.state.node_coordinator = _Coordinator()
    app.state.memory_write_queue = _Queue()
    app.state.memory_lease_manager = _LeaseManager()
    app.state.failover_state = _FailoverState()
    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["llm_provider"] == "configured"
    assert body["coordination"]["node_id"] == "node-1"
    assert body["coordination"]["peer_count"] == 2
    assert body["coordination"]["cluster"]["reachable_peers"] == 1
    assert body["memory"]["queue_size"] == 2
    assert body["memory"]["queue_pending"] == [{"id": "pending-1"}, {"id": "pending-2"}]
    assert body["memory"]["lease"]["owner_node_id"] == "node-1"
    assert body["sync"]["is_primary"] is True
    assert body["sync"]["memory_is_fresh"] is False
    assert body["failover"]["should_promote"] is True
