from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.anyio
async def test_ws_events_broadcasts_bot_stream_to_lan_peers():
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
    fake_bridge = MagicMock()
    fake_bridge.broadcast_event = AsyncMock(return_value={"sent": 1, "failed": 0})

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
        with client.websocket_connect("/api/ws/events") as ws:
            ws.send_text('{"type":"stream:content","data":{"session_id":"s1","text":"hola"}}')

    fake_bus.publish.assert_awaited_once_with("stream:content", {"session_id": "s1", "text": "hola"})
    fake_bridge.broadcast_event.assert_awaited_once_with("stream:content", {"session_id": "s1", "text": "hola"})
