from fastapi.testclient import TestClient


from web.server import app
from src.api.widgets import save_widget_state, get_widget_states
from src.api.messages import save_message_record, get_session_messages
from src.api.session import ensure_session
from src.memory.schema import init_db
from src.compressor import estimate_tokens, should_compress
from src.memory.repos import MessageRecord

client = TestClient(app)


def save_message(
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
    return save_message_record(MessageRecord(
        session_id=session_id,
        role=role,
        content=content,
        model=model,
        reasoning=reasoning,
        phases=phases,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    ))


def test_widget_db_operations():
    """Verify that widget states can be saved and retrieved from the database."""
    init_db()
    session_id = "test-session-widget-db"
    ensure_session(session_id)
    widget_id = "widget-calculator"
    state_data = '{"value": 42}'
    
    # Save the widget state
    save_widget_state(session_id, widget_id, state_data)
    
    # Retrieve states
    states = get_widget_states(session_id)
    assert widget_id in states
    assert states[widget_id] == state_data


def test_widget_endpoint_and_injection():
    """Verify the widget state API endpoint and script injection on session messages load."""
    init_db()
    session_id = "test-session-widget-api"
    ensure_session(session_id)
    widget_id = "widget-chart"
    state_data = '{"data": [1, 2, 3]}'
    
    # POST widget state
    post_resp = client.post(
        f"/sessions/{session_id}/widgets/{widget_id}/state",
        json={"state": state_data}
    )
    assert post_resp.status_code == 200
    assert post_resp.json() == {"status": "ok"}
    
    # GET session messages and verify data-widget-states is injected in the HTML response
    get_resp = client.get(f"/sessions/{session_id}/messages")
    assert get_resp.status_code == 200
    assert "data-widget-states" in get_resp.text
    # Verify the state data string is part of the metadata element
    assert widget_id in get_resp.text
    # The JSON string inside get_resp.text is escaped/formatted
    assert "[1, 2, 3]" in get_resp.text


def test_message_tokens_persistence():
    """Verify that message tokens are successfully persisted to SQLite and fetched."""
    init_db()
    session_id = "test-session-tokens-db"
    ensure_session(session_id)
    
    save_message(
        session_id=session_id,
        role="assistant",
        content="Hello world",
        model="big-pickle",
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120
    )
    
    # Retrieve messages from DB
    msgs = get_session_messages(session_id)
    assert len(msgs) == 1
    # Check that it saves and queries without errors
    # (role, content, model, created_at, reasoning, phases_str)
    # Wait, get_session_messages queries:
    # SELECT role, content, model, created_at, reasoning, phases FROM messages
    # Let's execute a direct sqlite query if we want to assert the token counts
    from src.memory.connection_pool import get_conn
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT prompt_tokens, completion_tokens, total_tokens FROM messages WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["prompt_tokens"] == 100
        assert row["completion_tokens"] == 20
        assert row["total_tokens"] == 120
    finally:
        conn.close()


def test_token_estimation_and_compression():
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


def test_widget_injection_xss_safety():
    """Verify that malicious XSS scripts in widget states are safely escaped in metadata."""
    init_db()
    session_id = "test-session-xss"
    ensure_session(session_id)
    widget_id = "widget-exploit"
    malicious_state = '{"payload": "<script>alert(1)</script>"}'
    
    # POST malicious state
    post_resp = client.post(
        f"/sessions/{session_id}/widgets/{widget_id}/state",
        json={"state": malicious_state}
    )
    assert post_resp.status_code == 200
    
    # GET session messages and verify it is HTML escaped
    get_resp = client.get(f"/sessions/{session_id}/messages")
    assert get_resp.status_code == 200
    # The raw <script> tag should NOT be present in the HTML response
    assert "<script>alert(1)</script>" not in get_resp.text
    # Instead, it should be escaped
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in get_resp.text
