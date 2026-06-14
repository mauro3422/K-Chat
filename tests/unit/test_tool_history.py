import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

from src.memory.repos import get_repos, Repositories
from src.tools.get_tool_history import run, DEFINITION


@pytest.mark.anyio
async def test_definition_structure():
    assert DEFINITION["type"] == "function"
    assert DEFINITION["function"]["name"] == "get_tool_history"


@pytest.mark.anyio
async def test_run_no_session():
    result = run(_session_id=None)
    assert "No active session" in result


@pytest.mark.anyio
async def test_run_empty_history():
    mock_repo = MagicMock()
    mock_repo.tool_calls.get_history.return_value = []
    result = run(_session_id="ses-1", _repos=mock_repo)
    assert "No tools have been used" in result
    mock_repo.tool_calls.get_history.assert_called_once_with("ses-1", limit=5)


@pytest.mark.anyio
async def test_run_with_results():
    mock_data = [
        {"tool_name": "web_search", "input": '{"query":"test"}', "status": "ok", "created_at": "2026-06-08T12:00:00", "turn": 0},
        {"tool_name": "save_memory", "input": '{"key":"x","value":"y"}', "status": "ok", "created_at": "2026-06-08T12:01:00", "turn": 0},
    ]
    mock_repo = MagicMock()
    mock_repo.tool_calls.get_history.return_value = mock_data
    result = run(_session_id="ses-1", _repos=mock_repo)
    assert "web_search" in result
    assert "save_memory" in result
    assert "ok" in result


@pytest.mark.anyio
async def test_run_limit_capped():
    mock_repo = MagicMock()
    mock_repo.tool_calls.get_history.return_value = []
    run(_session_id="ses-1", limit=50, _repos=mock_repo)
    mock_repo.tool_calls.get_history.assert_called_once_with("ses-1", limit=20)
