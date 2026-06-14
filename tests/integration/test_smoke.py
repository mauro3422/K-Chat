"""Smoke test — verify the app starts and critical endpoints respond."""
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


def _make_client():
    from web.server import app
    return TestClient(app, raise_server_exceptions=False)


@patch("web.routers.pages.get_available_model_ids", return_value=["test-model"])
def test_homepage_loads(_mock_models):
    client = _make_client()
    resp = client.get("/")
    assert resp.status_code == 200


@patch("web.routers.pages.get_available_model_ids", return_value=["test-model"])
def test_session_page_loads(_mock_models):
    client = _make_client()
    resp = client.get("/sessions/smoke-test-session")
    assert resp.status_code == 200



def test_sidebar_loads():
    client = _make_client()
    resp = client.get("/sidebar")
    assert resp.status_code == 200


def test_session_messages_empty():
    client = _make_client()
    resp = client.get("/sessions/smoke-test-session/messages")
    assert resp.status_code == 200


def test_debug_info():
    client = _make_client()
    resp = client.get("/sessions/smoke-test-session/debug")
    assert resp.status_code in (200, 404)


def test_health_endpoint():
    client = _make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_chat_returns_422_without_payload():
    client = _make_client()
    resp = client.post("/chat/smoke-test-session")
    assert resp.status_code == 422


@patch("web.routers.chat.build_stream_generator")
@patch("web.routers.chat.db_save_message")
@patch("web.routers.chat.rebuild_history", return_value=[])
@patch("web.routers.chat.ensure_session")
@patch("web.routers.chat.get_default_model", return_value="test-model")
def test_chat_streaming_works(_m1, _m2, _m3, _m4, mock_builder):
    mock_builder.return_value = lambda: iter([
        '{"t":"content","d":"Smoke test OK"}\n',
    ])
    client = _make_client()
    resp = client.post(
        "/chat/smoke-test-session",
        json={"message": "hello", "model": "test-model"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"
    lines = resp.text.strip().split("\n")
    assert any("Smoke test OK" in line for line in lines)
