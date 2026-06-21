from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.anyio
async def test_telegram_notify_records_reflection_state_and_status_endpoint():
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
    fake_bridge.broadcast_event = AsyncMock(return_value={"sent": 2, "failed": 0})
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
        app.state.node_bridge = fake_bridge

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/events/notify",
                json={"type": "new_message", "data": {"session_id": "tele_1", "source": {"node_id": "peer-a"}}},
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True

            status = client.get("/api/telegram/status")
            assert status.status_code == 200
            body = status.json()
            assert body["ok"] is True
            assert body["has_recent_reflection"] is True
            assert body["lan_total_sent"] == 2
            assert body["last_event"]["event_type"] == "new_message"
            assert body["last_event"]["path"] in {"notify", "lan"}
            assert body["recent_count"] >= 2
            fake_bridge.broadcast_event.assert_awaited_once()
            assert fake_bus.publish.await_count >= 1
