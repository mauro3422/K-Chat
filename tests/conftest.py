import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set temp DB paths BEFORE any module that imports config_loader.py is loaded.
# This ensures test DB isolation regardless of .env settings.
# NOTE: the actual env vars read by the code are SESSIONS_DB_PATH (for sessions.db)
# and KAIROS_MEMORY_DB_PATH (for memory.db), NOT "MEMORY_DB_PATH".
os.environ["SESSIONS_DB_PATH"] = "/tmp/kairos_test_sessions.db"
os.environ["KAIROS_MEMORY_DB_PATH"] = "/tmp/kairos_test_memory.db"
os.environ["OPENCODE_ZEN_API_KEY"] = "test-key-for-tests"
os.environ["SEARXNG_AUTO_START"] = "false"
os.environ["TESTING"] = "true"

import json
import tempfile
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from src.memory.schema import init_db


@pytest.fixture
def make_choice():
    """Build a mock ChatCompletion Choice."""
    def _make(content=None, finish_reason="stop", tool_calls=None, reasoning_content=None):
        msg = MagicMock()
        msg.content = content
        msg.reasoning_content = reasoning_content
        if tool_calls:
            tcs = []
            for tc in tool_calls:
                mock_tc = MagicMock()
                mock_tc.id = tc.get("id", "call_1")
                mock_tc.function.name = tc["name"]
                mock_tc.function.arguments = json.dumps(tc.get("args", {}))
                tcs.append(mock_tc)
            msg.tool_calls = tcs
        else:
            msg.tool_calls = None
        choice = MagicMock()
        choice.message = msg
        choice.finish_reason = finish_reason
        return choice
    return _make


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db(monkeypatch):
    """Fixture that isolates all databases during tests.

    Creates temp dirs for sessions.db AND memory.db, sets the correct
    env vars (``SESSIONS_DB_PATH`` and ``KAIROS_MEMORY_DB_PATH``), and
    cleans up both on teardown.

    NOTE: The old code used ``MEMORY_DB_PATH`` which is NOT read by
    any module — the correct env vars are ``SESSIONS_DB_PATH`` (for
    `db_path.py`) and ``KAIROS_MEMORY_DB_PATH`` (for `memory_db_path.py`).
    """
    temp_dir = tempfile.mkdtemp()
    sessions_db_path = os.path.join(temp_dir, "test_sessions.db")
    memory_db_path = os.path.join(temp_dir, "test_memory.db")

    monkeypatch.setenv("SESSIONS_DB_PATH", sessions_db_path)
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", memory_db_path)

    await init_db()

    yield sessions_db_path

    try:
        for path in (sessions_db_path, memory_db_path):
            if os.path.exists(path):
                os.remove(path)
        os.rmdir(temp_dir)
    except Exception:
        pass
