import pytest
from unittest.mock import AsyncMock
import json
from unittest.mock import MagicMock, patch

from src.tools._tool_parser import _parse_tool_call, _get_required_params


def _make_tc(name, arguments, tc_id="call_test_1"):
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return tc


TOOL_MAP = {"web_search": MagicMock(), "save_memory": MagicMock()}


@pytest.mark.anyio
async def test_parse_tool_call_valid():
    tc = _make_tc("web_search", {"query": "test"})
    name, args, error = _parse_tool_call(tc, TOOL_MAP)
    assert name == "web_search"
    assert args == {"query": "test"}
    assert error is None


@pytest.mark.anyio
async def test_parse_tool_call_corrupt_json():
    tc = _make_tc("web_search", "not-json{")
    name, args, error = _parse_tool_call(tc, TOOL_MAP)
    assert name == "web_search"
    assert args == {}
    assert error is not None
    assert "valid JSON object" in error


@pytest.mark.parametrize("arguments", ["null", "[]", '"query"'])
def test_parse_tool_call_rejects_non_object_json(arguments):
    tc = _make_tc("web_search", arguments)
    name, args, error = _parse_tool_call(tc, TOOL_MAP)

    assert name == "web_search"
    assert args == {}
    assert error == "[ERROR in web_search]: Tool arguments must be a JSON object."


@pytest.mark.anyio
async def test_parse_tool_call_empty_name():
    tc = _make_tc("", {"query": "test"})
    name, args, error = _parse_tool_call(tc, TOOL_MAP)
    assert name == ""
    assert error is not None
    assert "does not exist" in error


@pytest.mark.anyio
async def test_parse_tool_call_unknown_tool():
    tc = _make_tc("execute_action", {"query": "test"})
    name, args, error = _parse_tool_call(tc, TOOL_MAP)
    assert name == "execute_action"
    assert error is not None
    assert "does not exist" in error


@pytest.mark.anyio
async def test_get_required_params_existing_tool():
    with patch("src.tools.loader.TOOL_DEFINITIONS", {
        "web_search": {
            "function": {
                "name": "web_search",
                "parameters": {"required": ["query"]}
            }
        }
    }):
        result = _get_required_params("web_search")
        assert result == ["query"]


@pytest.mark.anyio
async def test_get_required_params_non_existing_tool():
    with patch("src.tools.loader.TOOL_DEFINITIONS", {}):
        result = _get_required_params("nonexistent_tool")
        assert result == []
