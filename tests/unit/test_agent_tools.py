"""Tests for agent tools: execute_command, list_files, search_files, web_search, fetch_url."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.tools import execute_command
from src.tools import list_files
from src.tools import search_files
from src.tools import web_search
from src.tools import fetch_url


class TestExecuteCommand:
    def test_definition_exists(self):
        assert execute_command.DEFINITION["function"]["name"] == "execute_command"

    def test_definition_has_command_param(self):
        params = execute_command.DEFINITION["function"]["parameters"]["properties"]
        assert "command" in params
        assert params["command"]["type"] == "string"

    def test_runs_simple_command(self, tmp_path):
        result = execute_command.run(command="echo hello", cwd=str(tmp_path))
        assert "hello" in result

    def test_error_on_empty_command(self):
        result = execute_command.run(command="  ")
        assert "[ERROR]" in result

    def test_error_on_nonexistent_command(self, tmp_path):
        result = execute_command.run(command="nonexistent_cmd_xyz_123", cwd=str(tmp_path))
        assert "[EXIT CODE:" in result or "[ERROR]" in result


class TestListFiles:
    def test_definition_exists(self):
        assert list_files.DEFINITION["function"]["name"] == "list_files"

    def test_definition_has_pattern_param(self):
        params = list_files.DEFINITION["function"]["parameters"]["properties"]
        assert "pattern" in params

    def test_glob_pattern(self, tmp_path):
        (tmp_path / "alpha.py").write_text("x = 1\n")
        (tmp_path / "beta.txt").write_text("hello\n")
        result = list_files.run(path=str(tmp_path), depth=0, pattern="*.py")
        assert "alpha.py" in result
        assert "beta.txt" not in result

    def test_empty_directory(self, tmp_path):
        result = list_files.run(path=str(tmp_path), depth=0)
        assert "0 files" in result or "directorio vacio" in result


class TestSearchFiles:
    def test_definition_exists(self):
        assert search_files.DEFINITION["function"]["name"] == "search_files"

    def test_definition_has_pattern_param(self):
        params = search_files.DEFINITION["function"]["parameters"]["properties"]
        assert "pattern" in params
        assert params["pattern"]["type"] == "string"

    def test_finds_content_in_files(self, tmp_path):
        (tmp_path / "test.txt").write_text("hello world\nfoo bar\n")
        result = search_files.run(pattern="hello", path=str(tmp_path))
        assert "hello" in result
        assert "hello world" in result

    def test_no_match_returns_empty(self, tmp_path):
        (tmp_path / "test.txt").write_text("hello world\n")
        result = search_files.run(pattern="zzz_nonexistent", path=str(tmp_path))
        assert "Sin coincidencias" in result

    def test_case_sensitivity(self, tmp_path):
        (tmp_path / "test.txt").write_text("Hello World\n")
        insensitive = search_files.run(pattern="hello", path=str(tmp_path), case_sensitive=False)
        sensitive = search_files.run(pattern="hello", path=str(tmp_path), case_sensitive=True)
        assert "Hello" in insensitive
        assert "Sin coincidencias" in sensitive

    def test_empty_pattern_returns_error(self):
        result = search_files.run(pattern="  ")
        assert "[ERROR]" in result

    def test_skip_binary_directories(self, tmp_path):
        (tmp_path / "file1.txt").write_text("hello world\n")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.py").write_text("hello\n")
        result = search_files.run(pattern="hello", path=str(tmp_path))
        assert "hello" in result
        assert "cached" not in result


MOCK_SEARCH_RESPONSE = {
    "results": [
        {
            "title": "Test Result",
            "content": "This is a test result content",
            "url": "https://example.com",
            "engine": "mock",
        }
    ],
    "suggestions": ["test suggestion"],
}


class TestWebSearch:
    def test_definition_exists(self):
        assert web_search.DEFINITION["function"]["name"] == "web_search"

    def test_definition_requires_query(self):
        required = web_search.DEFINITION["function"]["parameters"]["required"]
        assert "query" in required

    @patch("src.tools.web_search.httpx.get")
    def test_basic_search(self, mock_get):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = MOCK_SEARCH_RESPONSE
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = web_search.run(query="test query")
        assert "Search results" in result
        assert "Test Result" in result
        assert "This is a test result content" in result

    @patch("src.tools.web_search.httpx.get")
    def test_empty_query_returns_error(self, mock_get):
        result = web_search.run(query="")
        assert "[ERROR]" in result

    @patch("src.tools.web_search.httpx.get")
    def test_no_results(self, mock_get):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        result = web_search.run(query="nonexistent")
        assert "No results found" in result

    @patch("src.tools.web_search.httpx.get")
    def test_network_error_returns_error(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = web_search.run(query="failing query")
        assert "Search error" in result or "[ERROR]" in result

    @patch("src.tools.web_search.httpx.get")
    def test_suggestions_included(self, mock_get):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = MOCK_SEARCH_RESPONSE
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = web_search.run(query="test")
        assert "Suggestions" in result
        assert "test suggestion" in result


MOCK_HTML = """
<html><head><title>Test Page</title></head>
<body><p>Hello world content</p></body>
</html>
"""


class TestFetchUrl:
    def test_definition_exists(self):
        assert fetch_url.DEFINITION["function"]["name"] == "fetch_url"

    def test_definition_requires_url(self):
        required = fetch_url.DEFINITION["function"]["parameters"]["required"]
        assert "url" in required

    @patch("src.tools.fetch_url.httpx.get")
    def test_fetches_url(self, mock_get):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = MOCK_HTML.encode()
        mock_response.text = MOCK_HTML
        mock_response.url = httpx.URL("https://example.com")
        mock_response.history = []
        mock_get.return_value = mock_response

        result = fetch_url.run(url="https://example.com")
        assert "Test Page" in result
        assert "Hello world content" in result
        assert "Status: 200" in result

    @patch("src.tools.fetch_url.httpx.get")
    def test_empty_url_returns_error(self, mock_get):
        result = fetch_url.run(url="")
        assert "[ERROR]" in result

    @patch("src.tools.fetch_url.httpx.get")
    def test_binary_content_rejected(self, mock_get):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = b"fake binary data"
        mock_response.text = ""
        mock_response.url = httpx.URL("https://example.com/image.png")
        mock_response.history = []
        mock_get.return_value = mock_response

        result = fetch_url.run(url="https://example.com/image.png")
        assert "[ERROR]" in result

    @patch("src.tools.fetch_url.httpx.get")
    def test_http_error_returns_error(self, mock_get):
        mock_get.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock(status_code=404)
        )
        result = fetch_url.run(url="https://example.com/404")
        assert "HTTP 404" in result or "[ERROR]" in result
