from unittest.mock import AsyncMock
import pytest
from src.memory.schema import init_db
from src.api.session import ensure_session, get_sessions
from src.api.messages import get_session_messages, save_message_record
from src.api.tools import get_tool_history
from src.api.widgets import get_widget_states
from src.api.debug import get_debug_info
from src.memory.repos import MessageRecord, get_repos


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.anyio
async def test_schema_get_sessions():
    sessions = await get_sessions()
    assert isinstance(sessions, list)
    if sessions:
        assert isinstance(sessions[0], tuple)
        assert len(sessions[0]) >= 3


@pytest.mark.anyio
async def test_schema_get_session_messages():
    messages = await get_session_messages("nonexistent-session", repos=get_repos())
    assert isinstance(messages, list)
    if messages:
        assert isinstance(messages[0], tuple)


@pytest.mark.anyio
async def test_schema_get_tool_history():
    history = await get_tool_history("nonexistent-session", repos=get_repos())
    assert isinstance(history, list)
    if history:
        assert isinstance(history[0], tuple)


@pytest.mark.anyio
async def test_schema_get_widget_states():
    states = await get_widget_states("nonexistent-session")
    assert isinstance(states, dict)


@pytest.mark.anyio
async def test_schema_get_debug_info():
    info = await get_debug_info("nonexistent-session")
    assert isinstance(info, dict)


@pytest.mark.anyio
async def test_init_db_no_exception():
    await init_db()


@pytest.mark.anyio
async def test_ensure_session_creates_session():
    session_id = "contract-test-session"
    await ensure_session(session_id)
    messages = await get_session_messages(session_id, repos=get_repos())
    assert isinstance(messages, list)


@pytest.mark.anyio
async def test_save_message_accepts_record():
    session_id = "contract-test-record"
    await ensure_session(session_id)
    record = MessageRecord(
        session_id=session_id,
        role="user",
        content="test message",
        model="test-model",
    )
    await save_message_record(record, repos=get_repos())
    messages = await get_session_messages(session_id, repos=get_repos())
    assert len(messages) >= 1


@pytest.mark.anyio
async def test_save_message_record_explicit_contract():
    session_id = "contract-test-explicit-record"
    await ensure_session(session_id)
    await save_message_record(
        MessageRecord(
            session_id=session_id,
            role="assistant",
            content="explicit",
            model="test-model",
        ),
        repos=get_repos(),
    )
    messages = await get_session_messages(session_id, repos=get_repos())
    assert len(messages) >= 1
