import pytest
from fastapi.testclient import TestClient
from web.server import app
from src.memory.schema import init_db
from src.api.messages import save_message
from src.api.debug import save_debug_info

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Kairos" in response.text
    assert "session_id" in response.text or "sessionId" in response.text


def test_session_page():
    response = client.get("/sessions/test-session-123")
    assert response.status_code == 200
    assert "test-session-123" in response.text


def test_sidebar():
    response = client.get("/sidebar")
    assert response.status_code == 200
    assert "session-empty" in response.text or "session-item" in response.text


def test_session_messages_empty():
    response = client.get("/sessions/nonexistent-session/messages")
    assert response.status_code == 200
    assert "empty-state" in response.text or "messages" in response.text


def test_session_messages_with_data():
    session_id = "test-session-with-messages"
    save_message(session_id, "user", "Hello", "test-model")
    save_message(session_id, "assistant", "Hi there", "test-model")
    
    response = client.get(f"/sessions/{session_id}/messages")
    assert response.status_code == 200
    assert "Hello" in response.text or "Hi there" in response.text


def test_rename_session():
    session_id = "test-rename-session"
    save_message(session_id, "user", "test", "model")
    
    response = client.post(f"/sessions/{session_id}/rename", data={"name": "New Name"})
    assert response.status_code == 200


def test_delete_session():
    session_id = "test-delete-session"
    save_message(session_id, "user", "test", "model")
    
    response = client.post(f"/sessions/{session_id}/delete")
    assert response.status_code == 200


def test_widget_state_save():
    session_id = "test-widget-state"
    widget_id = "widget-1"
    
    response = client.post(
        f"/sessions/{session_id}/widgets/{widget_id}/state",
        json={"state": '{"value": 42}'}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_debug_info_empty():
    session_id = "test-debug-empty"
    response = client.get(f"/sessions/{session_id}/debug")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_debug_info_with_data():
    session_id = "test-debug-with-data"
    save_debug_info(session_id, {"model": "test", "reasoning": "thinking"})
    
    response = client.get(f"/sessions/{session_id}/debug")
    assert response.status_code == 200
    data = response.json()
    assert data.get("model") == "test"


def test_favicon():
    response = client.get("/favicon.ico")
    assert response.status_code == 200


def test_404_handler():
    response = client.get("/nonexistent-route")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


def test_validation_error():
    response = client.post("/sessions/test/rename", data={})
    assert response.status_code == 422
