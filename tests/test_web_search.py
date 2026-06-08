import os, sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.web_search import run, DEFINITION


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    assert DEFINITION["function"]["name"] == "web_search"
    assert "query" in DEFINITION["function"]["parameters"]["properties"]
    assert DEFINITION["function"]["parameters"]["required"] == ["query"]


@patch("src.tools.web_search.DDGS")
def test_run_returns_results(mock_ddgs):
    mock_instance = MagicMock()
    mock_instance.text.return_value = [
        {"title": "Result 1", "body": "Body 1", "href": "https://example.com/1"},
        {"title": "Result 2", "body": "Body 2", "href": "https://example.com/2"},
    ]
    mock_ddgs.return_value.__enter__.return_value = mock_instance

    result = run(query="test query")
    assert "Result 1" in result
    assert "Body 1" in result
    assert "Result 2" in result


@patch("src.tools.web_search.DDGS")
def test_run_empty_results(mock_ddgs):
    mock_instance = MagicMock()
    mock_instance.text.return_value = []
    mock_ddgs.return_value.__enter__.return_value = mock_instance

    result = run(query="nothing")
    assert "No se encontraron resultados" in result


@patch("src.tools.web_search.DDGS")
def test_run_retry_then_fail(mock_ddgs):
    mock_ddgs.return_value.__enter__.side_effect = Exception("API down")

    result = run(query="fail", _retries=1)
    assert "Error al buscar" in result
    assert mock_ddgs.return_value.__enter__.call_count == 2
