import pytest
from src.memory.schema import init_db
from src.api.session import ensure_session, get_sessions
from src.api.messages import get_session_messages, save_message
from src.api.tools import get_tool_history
from src.api.widgets import get_widget_states
from src.api.debug import get_debug_info
from src.memory.repos import MessageRecord


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_schema_get_sessions():
    sessions = get_sessions()
    assert isinstance(sessions, list)
    if sessions:
        assert isinstance(sessions[0], tuple)
        assert len(sessions[0]) >= 3


def test_schema_get_session_messages():
    messages = get_session_messages("nonexistent-session")
    assert isinstance(messages, list)
    if messages:
        assert isinstance(messages[0], tuple)


def test_schema_get_tool_history():
    history = get_tool_history("nonexistent-session")
    assert isinstance(history, list)
    if history:
        assert isinstance(history[0], tuple)


def test_schema_get_widget_states():
    states = get_widget_states("nonexistent-session")
    assert isinstance(states, dict)


def test_schema_get_debug_info():
    info = get_debug_info("nonexistent-session")
    assert isinstance(info, dict)


def test_init_db_no_exception():
    init_db()


def test_ensure_session_creates_session():
    session_id = "contract-test-session"
    ensure_session(session_id)
    messages = get_session_messages(session_id)
    assert isinstance(messages, list)


def test_save_message_accepts_record():
    session_id = "contract-test-record"
    record = MessageRecord(
        session_id=session_id,
        role="user",
        content="test message",
        model="test-model",
    )
    save_message(record)
    messages = get_session_messages(session_id)
    assert len(messages) >= 1
