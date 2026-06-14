from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from web.server import app
from src.memory.schema import init_db
from src.api.messages import save_message_record
from src.memory.repos import MessageRecord, get_repos
from src.api.debug import save_debug_info
from src.api.session import ensure_session

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def save_message(
    session_id,
    role,
    content,
    model,
    reasoning="",
    phases="[]",
    tool_calls=None,
    tool_call_id=None,
    **kwargs,
):
    return await save_message_record(MessageRecord(
        session_id=session_id,
        role=role,
        content=content,
        model=model,
        reasoning=reasoning,
        phases=phases,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    ), repos=get_repos())


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.anyio
async def test_home_page(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Kairos" in response.text
    assert 'data-session-id="' in response.text


@pytest.mark.anyio
async def test_session_page(client):
    response = await client.get("/sessions/test-session-123")
    assert response.status_code == 200
    assert "test-session-123" in response.text


@pytest.mark.anyio
async def test_sidebar(client):
    response = await client.get("/sidebar")
    assert response.status_code == 200
    assert "session-empty" in response.text or "session-item" in response.text


@pytest.mark.anyio
async def test_session_messages_empty(client):
    response = await client.get("/sessions/nonexistent-session/messages")
    assert response.status_code == 200
    assert "empty-state" in response.text or "messages" in response.text


@pytest.mark.anyio
async def test_session_messages_with_data(client):
    session_id = "test-session-with-messages"
    await ensure_session(session_id)
    await save_message(session_id, "user", "Hello", "test-model")
    await save_message(session_id, "assistant", "Hi there", "test-model")
    
    response = await client.get(f"/sessions/{session_id}/messages")
    assert response.status_code == 200
    assert "Hello" in response.text or "Hi there" in response.text


@pytest.mark.anyio
async def test_rename_session(client):
    session_id = "test-rename-session"
    await ensure_session(session_id)
    await save_message(session_id, "user", "test", "model")
    
    response = await client.post(f"/sessions/{session_id}/rename", json={"name": "New Name"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_delete_session(client):
    session_id = "test-delete-session"
    await ensure_session(session_id)
    await save_message(session_id, "user", "test", "model")
    
    response = await client.post(f"/sessions/{session_id}/delete")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_widget_state_save(client):
    session_id = "test-widget-state"
    await ensure_session(session_id)
    widget_id = "widget-1"
    
    response = await client.post(
        f"/sessions/{session_id}/widgets/{widget_id}/state",
        json={"state": '{"value": 42}'}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_debug_info_empty(client):
    session_id = "test-debug-empty"
    await ensure_session(session_id)
    response = await client.get(f"/sessions/{session_id}/debug")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


@pytest.mark.anyio
async def test_debug_info_with_data(client):
    session_id = "test-debug-with-data"
    await ensure_session(session_id)
    await save_debug_info(session_id, {"model": "test", "reasoning": "thinking"})
    
    response = await client.get(f"/sessions/{session_id}/debug")
    assert response.status_code == 200
    data = response.json()
    assert data.get("model") == "test"


@pytest.mark.anyio
async def test_favicon(client):
    response = await client.get("/favicon.ico")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_404_handler(client):
    response = await client.get("/nonexistent-route")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.anyio
async def test_validation_error(client):
    response = await client.post("/sessions/test/rename", data={})
    assert response.status_code == 422
