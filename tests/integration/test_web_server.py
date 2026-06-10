from unittest.mock import patch
from fastapi.testclient import TestClient


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
    assert "Send a message to start" in response.text

@patch("web.services.chat_stream.chat_stream")
def test_chat_streaming(mock_chat_stream):
    """Verify that /chat streaming returns NDJSON lines."""
    # Mocking chat_stream to yield reasoning and content tokens
    mock_chat_stream.return_value = [
        ("reasoning", "Thinking..."),
        ("content", "Hello from mocked LLM"),
    ]
    
    response = client.post(
        "/chat/test-session-abc",
        json={"message": "hello", "model": "test-model"}
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

def test_session_messages_filtering():
    """Verify that intermediate assistant messages and tool messages are filtered out in UI."""
    from src.memory.database import init_db
    from src.api import save_message
    init_db()
    session_id = "test-session-filtering"
    
    # 1. Save messages representing a multi-step turn
    save_message(session_id, "user", "run test", "model")
    save_message(session_id, "assistant", "intermediate response 1", "model", tool_calls='[{"id": "call_1", "type": "function", "function": {"name": "save_memory", "arguments": "{}"}}]')
    save_message(session_id, "tool", "tool result 1", model=None, tool_call_id="call_1")
    save_message(session_id, "assistant", "final response content", "model", phases='[{"reasoning": "thought", "tool_ids": ["call_1"], "content": "final response content"}]')
    
    # 2. Get messages endpoint response
    response = client.get(f"/sessions/{session_id}/messages")
    assert response.status_code == 200
    
    # The intermediate message "intermediate response 1" should be filtered out
    # because there is a subsequent final assistant message in the same turn.
    assert "intermediate response 1" not in response.text
    
    # Tool outputs should never render as standard message blocks
    assert "tool result 1" not in response.text
    
    # The user message and final assistant message must be present
    assert "run test" in response.text
    assert "final response content" in response.text

