import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock, mock_open


def _make_registry(mock_defs):
    mock_registry = MagicMock()
    type(mock_registry).definitions = property(lambda self: mock_defs)
    return mock_registry


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

    with patch("src.tools.get_default_registry", return_value=_make_registry(mock_defs)):
        from src.context.tools_docs import _build_tools_md

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
    with patch("src.tools.get_default_registry", return_value=_make_registry({})):
        from src.context.tools_docs import _build_tools_md

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

    with patch("src.tools.get_default_registry", return_value=_make_registry(mock_defs)):
        from src.context.tools_docs import _build_tools_md

        result = _build_tools_md()

        assert "limit=5" in result
        assert "(optional)" in result
        assert "(integer)" in result


@pytest.mark.anyio
async def test_auto_section_generates_table():
    mock_fn = {
        "description": "Test tool",
        "parameters": {
            "properties": {
                "param1": {"type": "string", "description": "First param"},
                "param2": {"type": "integer", "description": "Second param", "default": 10},
            },
            "required": ["param1"],
        },
    }

    from src.context.tools_docs import _auto_section

    result = _auto_section("test_tool", mock_fn)

    assert "# test_tool" in result
    assert "**Test tool**" in result
    assert "<!-- auto:params -->" in result
    assert "| Parámetro | Tipo | Requerido | Default | Descripción |" in result
    assert "|---|---|---|---|---|" in result
    assert "| `param1` | string | Sí |  | First param |" in result
    assert "| `param2` | integer | No | 10 | Second param |" in result


@pytest.mark.anyio
async def test_build_rules_files_creates_files():
    mock_defs = {
        "tool1": {
            "function": {
                "name": "tool1",
                "description": "First tool",
                "parameters": {
                    "properties": {
                        "param1": {"type": "string"},
                    },
                },
            },
        },
        "tool2": {
            "function": {
                "name": "tool2",
                "description": "Second tool",
                "parameters": {
                    "properties": {
                        "param2": {"type": "integer"},
                    },
                },
            },
        },
    }

    with patch("src.tools.get_default_registry", return_value=_make_registry(mock_defs)):
        with patch("os.path.exists", return_value=False):
            with patch("builtins.open", mock_open()) as mock_file:
                from src.context.tools_docs import _build_rules_files

                _build_rules_files("/tmp/rules")

                assert mock_file().write.call_count == 2


@pytest.mark.anyio
async def test_build_rules_files_preserves_manual_section():
    mock_defs = {
        "tool1": {
            "function": {
                "name": "tool1",
                "description": "First tool",
                "parameters": {
                    "properties": {
                        "param1": {"type": "string"},
                    },
                },
            },
        },
    }

    existing_content = """# tool1
**First tool**
<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `param1` | string | No |  | First param |
---

Manual section below
"""

    with patch("src.tools.get_default_registry", return_value=_make_registry(mock_defs)):
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=existing_content)) as mock_file:
                from src.context.tools_docs import _build_rules_files

                _build_rules_files("/tmp/rules")

                write_calls = mock_file().write.call_args_list
                assert len(write_calls) >= 1

                all_written = "".join(call[0][0] for call in write_calls)
                assert "# tool1" in all_written
                assert "**First tool**" in all_written
                assert "<!-- auto:params -->" in all_written
                assert "Manual section below" in all_written
