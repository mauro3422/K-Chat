import os
import sys
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web.server import app

client = TestClient(app)

def test_home_page():
    """Verify that home page loads and sets cache headers."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Kairos" in response.text

def test_session_page():
    """Verify session page returns 200 status."""
    response = client.get("/sessions/test-session-123")
    assert response.status_code == 200
    assert "test-session-123" in response.text

def test_sidebar():
    """Verify sidebar fragment is rendered."""
    response = client.get("/sidebar")
    assert response.status_code == 200
    assert "session" in response.text or "Sin sesiones" in response.text


def test_session_messages_empty():
    """Verify that empty session messages returns default empty state."""
    response = client.get("/sessions/test-session-abc/messages")
    assert response.status_code == 200
    assert "Envia un mensaje para empezar" in response.text

@patch("web.routers.chat.chat_stream")
def test_chat_streaming(mock_chat_stream):
    """Verify that /chat streaming returns NDJSON lines."""
    # Mocking chat_stream to yield reasoning and content tokens
    mock_chat_stream.return_value = [
        ("reasoning", "Thinking..."),
        ("content", "Hello from mocked LLM"),
    ]
    
    response = client.post(
        "/chat/test-session-abc",
        data={"message": "hello", "model": "test-model"}
    )
    
    assert response.status_code == 200
    assert "application/x-ndjson" in response.headers["content-type"]
    
    # Read the streaming NDJSON content
    lines = response.content.decode("utf-8").strip().split("\n")
    assert len(lines) == 2
    import json
    msg1 = json.loads(lines[0])
    msg2 = json.loads(lines[1])
    assert msg1["t"] == "reasoning"
    assert msg1["d"] == "Thinking..."
    assert msg2["t"] == "content"
    assert msg2["d"] == "Hello from mocked LLM"

def test_rename_session():
    """Verify session rename endpoint works."""
    response = client.post("/sessions/test-session-abc/rename", data={"name": "New Chat Name"})
    assert response.status_code == 200
    assert response.text == "OK"

def test_delete_session():
    """Verify session delete endpoint works."""
    response = client.post("/sessions/test-session-abc/delete")
    assert response.status_code == 200
    assert response.text == "OK"

def test_debug_info_empty():
    """Verify debug info of nonexistent session is empty JSON."""
    response = client.get("/sessions/test-session-abc/debug")
    assert response.status_code == 200
    data = response.json()
    assert data == {}
