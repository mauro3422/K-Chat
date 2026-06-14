import pytest
from unittest.mock import AsyncMock
"""Smoke test — verify the app starts and critical endpoints respond."""
from unittest.mock import patch, MagicMock

from httpx import AsyncClient, ASGITransport
from web.server import app

def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@patch("web.routers.pages.get_available_model_ids", return_value=["test-model"])
@pytest.mark.anyio
async def test_homepage_loads(_mock_models):
    async with _make_client() as client:
        resp = await client.get("/")
    assert resp.status_code == 200


@patch("web.routers.pages.get_available_model_ids", return_value=["test-model"])
@pytest.mark.anyio
async def test_session_page_loads(_mock_models):
    async with _make_client() as client:
        resp = await client.get("/sessions/smoke-test-session")
    assert resp.status_code == 200



@pytest.mark.anyio
async def test_sidebar_loads():
    async with _make_client() as client:
        resp = await client.get("/sidebar")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_session_messages_empty():
    async with _make_client() as client:
        resp = await client.get("/sessions/smoke-test-session/messages")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_debug_info():
    from src.memory.schema import init_db
    from src.api.session import ensure_session
    await init_db()
    await ensure_session("smoke-test-session")
    async with _make_client() as client:
        resp = await client.get("/sessions/smoke-test-session/debug")
    assert resp.status_code in (200, 404)


@pytest.mark.anyio
async def test_health_endpoint():
    async with _make_client() as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_chat_returns_422_without_payload():
    async with _make_client() as client:
        resp = await client.post("/chat/smoke-test-session")
    assert resp.status_code == 422


@patch("web.routers.chat.build_stream_generator")
@patch("web.routers.chat.rebuild_history", return_value=[])
@patch("web.routers.chat.get_default_model", return_value="test-model")
@pytest.mark.anyio
async def test_chat_streaming_works(_mock_default, _mock_history, mock_builder):
    from src.memory.schema import init_db
    from src.api.session import ensure_session
    await init_db()
    await ensure_session("smoke-test-session")
    mock_builder.return_value = lambda: iter([
        '{"t":"content","d":"Smoke test OK"}\n',
    ])
    async with _make_client() as client:
        resp = await client.post(
            "/chat/smoke-test-session",
            data={"message": "hello", "model": "test-model"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"
    lines = resp.text.strip().split("\n")
    assert any("Smoke test OK" in line for line in lines)
