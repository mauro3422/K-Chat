from unittest.mock import patch, MagicMock

from src.memory.repos import get_repos, Repositories
from src.tools.get_tool_history import run, DEFINITION


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    assert DEFINITION["function"]["name"] == "get_tool_history"


def test_run_no_session():
    result = run(_session_id=None)
    assert "No active session" in result


def test_run_empty_history():
    mock_repo = MagicMock()
    mock_repo.tool_calls.get_history.return_value = []
    with patch("src.tools.get_tool_history.get_repos", return_value=mock_repo):
        result = run(_session_id="ses-1")
    assert "No tools have been used" in result
    mock_repo.tool_calls.get_history.assert_called_once_with("ses-1", limit=5)


def test_run_with_results():
    mock_data = [
        {"tool_name": "web_search", "input": '{"query":"test"}', "status": "ok", "created_at": "2026-06-08T12:00:00", "turn": 0},
        {"tool_name": "save_memory", "input": '{"key":"x","value":"y"}', "status": "ok", "created_at": "2026-06-08T12:01:00", "turn": 0},
    ]
    mock_repo = MagicMock()
    mock_repo.tool_calls.get_history.return_value = mock_data
    with patch("src.tools.get_tool_history.get_repos", return_value=mock_repo):
        result = run(_session_id="ses-1")
    assert "web_search" in result
    assert "save_memory" in result
    assert "ok" in result


def test_run_limit_capped():
    mock_repo = MagicMock()
    mock_repo.tool_calls.get_history.return_value = []
    with patch("src.tools.get_tool_history.get_repos", return_value=mock_repo):
        run(_session_id="ses-1", limit=50)
    mock_repo.tool_calls.get_history.assert_called_once_with("ses-1", limit=20)
