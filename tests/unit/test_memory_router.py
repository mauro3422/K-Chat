import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.coordination.node_state import NodeCoordinator


@pytest.mark.anyio
async def test_memory_compare_endpoint_calls_manage_memory():
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
        app.state.manage_memory_run = AsyncMock(return_value="[OK] compare")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/memory/compare?key_pattern=user:*&fmt=json")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["result"] == "[OK] compare"
        app.state.manage_memory_run.assert_awaited_once()


@pytest.mark.anyio
async def test_memory_sync_endpoint_calls_manage_memory():
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
        app.state.manage_memory_run = AsyncMock(return_value="[OK] sync")
        app.state.event_bus = AsyncMock()
        app.state.event_bus.publish = AsyncMock()

    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("web.routers.memory.log_event") as mock_log:
            response = client.post("/api/memory/sync", json={"dry_run": False, "confirm": True})
        assert response.status_code == 200
        assert response.json()["result"] == "[OK] sync"
        app.state.manage_memory_run.assert_awaited_once()
        assert app.state.node_coordinator.snapshot()["last_memory_sync"] > 0
        app.state.event_bus.publish.assert_awaited_once()
        mock_log.assert_called_once()


@pytest.mark.anyio
async def test_memory_sync_dry_run_does_not_mark_state():
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
        app.state.manage_memory_run = AsyncMock(return_value="[DRY RUN] sync")
        app.state.event_bus = AsyncMock()
        app.state.event_bus.publish = AsyncMock()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/memory/sync", json={"dry_run": True, "confirm": True})
        assert response.status_code == 200
        assert response.json()["result"] == "[DRY RUN] sync"
        app.state.manage_memory_run.assert_awaited_once()
        assert app.state.node_coordinator.snapshot()["last_memory_sync"] == 0.0
        app.state.event_bus.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_memory_status_endpoint_reports_queue_and_lease():
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
        response = client.get("/api/memory/status")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["queue_size"] == 0
        assert body["queue_path"]
        assert body["lease"] is None


@pytest.mark.anyio
async def test_memory_diagnostics_endpoint_reports_compare_and_freshness():
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
        "only_in_db": ["Orphan"],
        "mismatched": [{"key": "Modo", "md": "A", "db": "B", "db_updated_at": "2026-06-19T10:00:00"}],
        "rename_candidates": [{"orphan": "Orphan", "target": "Preferencia", "score": 0.91, "ambiguous": False}],
        "matched": 1,
        "md_total": 2,
        "db_total": 2,
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
        coordinator = NodeCoordinator(fake_config)
        await coordinator.mark_memory_revision({"event": "test"})
        await coordinator.mark_memory_sync({"event": "seed"})
        app.state.node_coordinator = coordinator

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/memory/diagnostics?key_pattern=user:*")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["compare"]["rename_candidates"][0]["target"] == "Preferencia"
        assert body["compare"]["only_in_db"] == ["Orphan"]
        assert body["compare_summary"]["severity"] == "high"
        assert "revisión manual de renombres ambiguos" not in body["compare_summary"]["actions"]
        assert body["memory"]["is_fresh"] is False
        assert body["queue_path"]
        app.state.manage_memory_run.assert_awaited_once()


@pytest.mark.anyio
async def test_memory_conflicts_endpoint_summarizes_actions():
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
        "only_in_db": ["Orphan"],
        "mismatched": [{"key": "Modo", "md": "A", "db": "B", "db_updated_at": "2026-06-19T10:00:00"}],
        "rename_candidates": [{"orphan": "Orphan", "target": "Preferencia", "score": 0.91, "ambiguous": True}],
        "matched": 1,
        "md_total": 2,
        "db_total": 2,
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

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/memory/conflicts?key_pattern=user:*")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["summary"]["has_conflicts"] is True
        assert body["summary"]["severity"] == "high"
        assert body["summary"]["counts"]["ambiguous_renames"] == 1
        assert any("renombres ambiguos" in action for action in body["summary"]["actions"])
        assert body["queue"]["size"] == 0
        app.state.manage_memory_run.assert_awaited_once()
