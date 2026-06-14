import pytest
from unittest.mock import AsyncMock, MagicMock
import os
from unittest.mock import patch, mock_open

from src.paths import CONTEXT_DIR


@pytest.mark.anyio
async def test_ensure_file_creates():
    from src.context import _ensure_file

    with patch("os.path.exists", return_value=False):
        with patch("builtins.open", mock_open()) as m:
            _ensure_file("/tmp/test.md", "# content")
            m.assert_called_once_with("/tmp/test.md", "w", encoding="utf-8")
            m().write.assert_called_once_with("# content")


@pytest.mark.anyio
async def test_ensure_file_exists():
    from src.context import _ensure_file

    with patch("os.path.exists", return_value=True):
        with patch("builtins.open") as m:
            _ensure_file("/tmp/test.md", "# content")
            m.assert_not_called()


@pytest.mark.anyio
async def test_ensure_file_oserror():
    from src.context import _ensure_file

    with patch("os.path.exists", return_value=False):
        with patch("builtins.open", side_effect=OSError("permission denied")):
            _ensure_file("/tmp/test.md", "# content")


@pytest.mark.anyio
async def test_read_file_normal():
    from src.context import _read_file

    with patch("builtins.open", mock_open(read_data="  hello world  ")):
        result = _read_file("/tmp/test.md")
        assert result == "hello world"


@pytest.mark.anyio
async def test_read_file_missing():
    from src.context import _read_file

    with patch("builtins.open", side_effect=FileNotFoundError("no such file")):
        result = _read_file("/tmp/missing.md")
        assert result == ""


@pytest.mark.anyio
async def test_build_tools_md_with_tools():
    mock_defs = {
        "web_search": {
            "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query"},
                        "max_results": {"type": "integer", "description": "Max result count"},
                    },
                    "required": ["query"],
                },
            },
        },
        "read_file": {
            "function": {
                "name": "read_file",
                "description": "Read a file from disk",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            },
        },
    }

    mock_registry = MagicMock()
    mock_registry.definitions = mock_defs
    with patch("src.tools.get_default_registry", return_value=mock_registry):
        from src.context import _build_tools_md

        result = _build_tools_md()

        assert "# Available Tools" in result
        assert "read_file" in result
        assert "web_search" in result
        assert "Search the web" in result
        assert "Read a file from disk" in result
        assert "query" in result
        assert "max_results" in result
        assert "path" in result
        assert "(required)" in result
        assert "(optional)" in result
        assert 'query="example query"' in result
        assert "max_results=5" in result
        assert 'path="example path"' in result


@pytest.mark.anyio
async def test_build_tools_md_empty():
    mock_registry = MagicMock()
    mock_registry.definitions = {}
    with patch("src.tools.get_default_registry", return_value=mock_registry):
        from src.context import _build_tools_md

        result = _build_tools_md()
        assert "# Available Tools" in result
        assert "These are the internal tools" in result
        assert "**" not in result[len("# Available Tools\n"):]


@pytest.mark.anyio
async def test_build_tools_md_integer_param():
    mock_defs = {
        "get_tool_history": {
            "function": {
                "name": "get_tool_history",
                "description": "View tool usage history",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of entries"},
                    },
                    "required": [],
                },
            },
        },
    }

    mock_registry = MagicMock()
    mock_registry.definitions = mock_defs
    with patch("src.tools.get_default_registry", return_value=mock_registry):
        from src.context import _build_tools_md

        result = _build_tools_md()

        assert "limit=5" in result
        assert "(optional)" in result
        assert "(integer)" in result


@pytest.mark.anyio
async def test_load_context():
    content_map = {
        os.path.join(CONTEXT_DIR, "SOUL.md"): "# Soul content",
        os.path.join(CONTEXT_DIR, "MEMORY.md"): "# Memory content",
        os.path.join(CONTEXT_DIR, "AGENTS.md"): "# Agents content",
    }

    with patch("src.context.builder._ensure_file") as mock_ensure:
        with patch("src.context.builder._read_file", side_effect=lambda p: content_map.get(p, "")):
            from src.context import load_context

            result = load_context()

            assert mock_ensure.call_count == 3
            assert result == "# Soul content\n\n# Memory content\n\n# Agents content"


@pytest.mark.anyio
async def test_build_system_prompt():
    from src.context.runtime import ContextSnapshot

    with patch("src.context.builder.build_context_snapshot",
               return_value=ContextSnapshot(text="MOCKED CONTEXT", tools_md="")):
        from src.context import build_system_prompt

        result = build_system_prompt("gpt-4-test")

        assert result["role"] == "system"
        assert "gpt-4-test" in result["content"]
        assert "MOCKED CONTEXT" in result["content"]
        assert "Kairos" in result["content"]
        assert "System time:" in result["content"]
