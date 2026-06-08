import os, sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.get_tool_history import run, DEFINITION


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    assert DEFINITION["function"]["name"] == "get_tool_history"


def test_run_no_session():
    result = run(_session_id=None)
    assert "No hay sesion activa" in result


@patch("src.tools.get_tool_history._get_tool_history")
def test_run_empty_history(mock_get):
    mock_get.return_value = []
    result = run(_session_id="ses-1")
    assert "No se usaron herramientas" in result
    mock_get.assert_called_once_with("ses-1", limit=5)


@patch("src.tools.get_tool_history._get_tool_history")
def test_run_with_results(mock_get):
    mock_get.return_value = [
        ("web_search", '{"query":"test"}', "ok", "2026-06-08T12:00:00", 0),
        ("save_memory", '{"key":"x","value":"y"}', "ok", "2026-06-08T12:01:00", 0),
    ]
    result = run(_session_id="ses-1")
    assert "web_search" in result
    assert "save_memory" in result
    assert "ok" in result


@patch("src.tools.get_tool_history._get_tool_history")
def test_run_limit_capped(mock_get):
    run(_session_id="ses-1", limit=50)
    mock_get.assert_called_once_with("ses-1", limit=20)
