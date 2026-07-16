import os

import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock, mock_open


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

    from src.context.tools_docs import _build_tools_md

    result = _build_tools_md(mock_defs)

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
    from src.context.tools_docs import _build_tools_md

    result = _build_tools_md({})
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

    from src.context.tools_docs import _build_tools_md

    result = _build_tools_md(mock_defs)

    assert "limit=5" in result
    assert "(optional)" in result
    assert "(integer)" in result


@pytest.mark.anyio
async def test_build_tools_md_preserves_falsy_defaults():
    mock_defs = {
        "toggle_tool": {
            "function": {
                "name": "toggle_tool",
                "description": "Toggle a flag",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "description": "Counter", "default": 0},
                        "enabled": {"type": "boolean", "description": "Feature switch", "default": False},
                    },
                    "required": [],
                },
            },
        },
    }

    from src.context.tools_docs import _build_tools_md

    result = _build_tools_md(mock_defs)

    assert "count=0" in result
    assert "enabled=false" in result
    assert "count=5" not in result
    assert "enabled=5" not in result


@pytest.mark.anyio
async def test_auto_section_includes_numeric_bounds():
    mock_fn = {
        "description": "Test tool",
        "parameters": {
            "properties": {
                "limit": {"type": "integer", "description": "Number of entries", "default": 10, "minimum": 1, "maximum": 20},
            },
            "required": [],
        },
    }

    from src.context.tools_docs import _auto_section

    result = _auto_section("test_tool", mock_fn)

    assert "Range: 1..20" in result
    assert "| `limit` | integer | No | 10 | Number of entries Range: 1..20 |" in result


@pytest.mark.anyio
async def test_auto_section_formats_boolean_defaults_lowercase():
    mock_fn = {
        "description": "Test tool",
        "parameters": {
            "properties": {
                "flag": {"type": "boolean", "description": "Feature flag", "default": False},
            },
            "required": [],
        },
    }

    from src.context.tools_docs import _auto_section

    result = _auto_section("test_tool", mock_fn)

    assert "| `flag` | boolean | No | false | Feature flag |" in result


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
    assert "| Par\u00e1metro | Tipo | Requerido | Default | Descripci\u00f3n |" in result
    assert "|---|---|---|---|---|" in result
    assert "| `param1` | string | S\u00ed |  | First param |" in result
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

    with patch("os.path.exists", return_value=False):
        with patch("builtins.open", mock_open()) as mock_file:
            from src.context.tools_docs import _build_rules_files

            _build_rules_files("/tmp/rules", mock_defs)

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
| Par\u00e1metro | Tipo | Requerido | Default | Descripci\u00f3n |
|---|---|---|---|---|
| `param1` | string | No |  | First param |
---

Manual section below
"""

    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=existing_content)) as mock_file:
            from src.context.tools_docs import _build_rules_files

            _build_rules_files("/tmp/rules", mock_defs)

            write_calls = mock_file().write.call_args_list
            assert len(write_calls) >= 1

            all_written = "".join(call[0][0] for call in write_calls)
            assert "# tool1" in all_written
            assert "**First tool**" in all_written
            assert "<!-- auto:params -->" in all_written
            assert "Manual section below" in all_written


@pytest.mark.anyio
async def test_rules_files_match_registry_definitions():
    from src.context.tools_docs import _auto_section
    from src.paths import CONTEXT_DIR
    from src.tools import get_default_registry

    rules_dir = os.path.join(CONTEXT_DIR, "rules")
    registry = get_default_registry().definitions

    for name, defn in sorted(registry.items()):
        path = os.path.join(rules_dir, f"{name}.md")
        assert os.path.exists(path), f"Missing generated rules file for {name}"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        expected_auto = _auto_section(name, defn["function"])
        assert content.startswith(expected_auto), f"Outdated rules file for {name}"
