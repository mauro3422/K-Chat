import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set a temp DB path BEFORE any module that imports config_loader.py is loaded.
# This ensures test DB isolation regardless of .env settings.
os.environ["MEMORY_DB_PATH"] = "/tmp/kairos_test.db"
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
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    monkeypatch.setenv("MEMORY_DB_PATH", db_path)

    await init_db()

    yield db_path

    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)
    except Exception:
        pass
