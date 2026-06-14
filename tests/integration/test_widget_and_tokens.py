import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from web.server import app
from src.api.widgets import save_widget_state, get_widget_states
from src.api.messages import save_message_record, get_session_messages
from src.api.session import ensure_session
from src.memory.schema import init_db
from src.compressor import estimate_tokens, should_compress
from src.memory.repos import MessageRecord, get_repos

def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def save_message(
    session_id,
    role,
    content,
    model,
    reasoning="",
    phases="[]",
    tool_calls=None,
    tool_call_id=None,
    prompt_tokens=0,
    completion_tokens=0,
    total_tokens=0,
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
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    ), repos=get_repos())


@pytest.mark.anyio
async def test_widget_db_operations():
    """Verify that widget states can be saved and retrieved from the database."""
    await init_db()
    session_id = "test-session-widget-db"
    await ensure_session(session_id)
    widget_id = "widget-calculator"
    state_data = '{"value": 42}'
    
    # Save the widget state
    await save_widget_state(session_id, widget_id, state_data)
    
    # Retrieve states
    states = await get_widget_states(session_id)
    assert widget_id in states
    assert states[widget_id] == state_data


@pytest.mark.anyio
async def test_widget_endpoint_and_injection():
    """Verify the widget state API endpoint and script injection on session messages load."""
    await init_db()
    session_id = "test-session-widget-api"
    await ensure_session(session_id)
    widget_id = "widget-chart"
    state_data = '{"data": [1, 2, 3]}'
    
    # POST widget state
    async with _make_client() as client:
        post_resp = await client.post(
            f"/sessions/{session_id}/widgets/{widget_id}/state",
            json={"state": state_data}
        )
        assert post_resp.status_code == 200
        assert post_resp.json() == {"status": "ok"}
        
        # GET session messages and verify data-widget-states is returned in JSON
        get_resp = await client.get(f"/sessions/{session_id}/messages")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "widget_states" in data
        assert widget_id in data["widget_states"]
        assert "[1, 2, 3]" in data["widget_states"][widget_id]


@pytest.mark.anyio
async def test_message_tokens_persistence():
    """Verify that message tokens are successfully persisted to SQLite and fetched."""
    await init_db()
    session_id = "test-session-tokens-db"
    await ensure_session(session_id)
    
    await save_message(
        session_id=session_id,
        role="assistant",
        content="Hello world",
        model="big-pickle",
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120
    )
    
    # Retrieve messages from DB
    msgs = await get_session_messages(session_id, repos=get_repos())
    assert len(msgs) == 1
    
    # Check that it saves and queries without errors
    from src.memory.connection_pool import get_conn
    conn = await get_conn()
    try:
        cursor = await conn.cursor()
        await cursor.execute("SELECT prompt_tokens, completion_tokens, total_tokens FROM messages WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()
        assert row is not None
        assert row["prompt_tokens"] == 100
        assert row["completion_tokens"] == 20
        assert row["total_tokens"] == 120
    finally:
        await conn.close()


@pytest.mark.anyio
async def test_token_estimation_and_compression():
    """Verify estimate_tokens and should_compress logic in compressor.py."""
    assert estimate_tokens("hello") == 1
    assert estimate_tokens("hello world") == 2
    assert estimate_tokens("") == 0
    
    # Empty/small history should not compress
    history = [
        {"role": "system", "content": "You are Kairos"},
        {"role": "user", "content": "Hi"}
    ]
    assert should_compress(history) is False
    
    # Large content history should trigger compression
    large_history = [
        {"role": "system", "content": "You are Kairos"},
        {"role": "user", "content": "A" * 25000} # ~6250 tokens
    ]
    assert should_compress(large_history) is True


@pytest.mark.anyio
async def test_widget_injection_xss_safety():
    """Verify that malicious XSS scripts in widget states are returned in the JSON payload."""
    await init_db()
    session_id = "test-session-xss"
    await ensure_session(session_id)
    widget_id = "widget-exploit"
    malicious_state = '{"payload": "<script>alert(1)</script>"}'
    
    async with _make_client() as client:
        # POST malicious state
        post_resp = await client.post(
            f"/sessions/{session_id}/widgets/{widget_id}/state",
            json={"state": malicious_state}
        )
        assert post_resp.status_code == 200
        
        # GET session messages and verify it is returned in JSON
        get_resp = await client.get(f"/sessions/{session_id}/messages")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["widget_states"][widget_id] == malicious_state
