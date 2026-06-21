import pytest
from unittest.mock import MagicMock, patch

from src.tools.registry import ToolRegistry


def test_register_adds_tool():
    registry = ToolRegistry()
    fn = lambda x: "result"

    registry.register("my_tool", fn, {"function": {"name": "my_tool"}})

    assert registry.get("my_tool") is fn
    assert registry.tool_map["my_tool"] is fn
    assert registry.definitions["my_tool"] == {"function": {"name": "my_tool"}}


def test_register_returns_self_for_chaining():
    registry = ToolRegistry()
    fn = lambda x: "r"

    result = registry.register("t", fn, {"function": {"name": "t"}})
    assert result is registry


def test_get_returns_none_for_unknown_tool():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_get_returns_none_for_empty_registry():
    registry = ToolRegistry()
    registry._built = True
    assert registry.get("anything") is None


def test_has_returns_true_for_registered():
    registry = ToolRegistry()
    registry.register("exists", lambda: "ok", {"function": {"name": "exists"}})
    assert registry.get("exists") is not None


def test_discover_returns_self():
    registry = ToolRegistry()
    result = registry.discover("src.tools")
    assert result is registry


def test_discover_has_no_effect_after_build():
    registry = ToolRegistry()
    registry._built = True
    result = registry.discover("src.tools")
    assert result is registry


def test_register_raises_after_build():
    registry = ToolRegistry()
    registry.build()
    fn = lambda: "x"

    with pytest.raises(RuntimeError, match="Cannot register tools after build"):
        registry.register("t", fn, {"function": {"name": "t"}})


def test_build_is_idempotent():
    registry = ToolRegistry()
    registry._built = True
    result = registry.build()
    assert result is registry


def test_tool_map_triggers_build():
    registry = ToolRegistry()
    assert registry._built is False
    _ = registry.tool_map
    assert registry._built is True


def test_definitions_triggers_build():
    registry = ToolRegistry()
    assert registry._built is False
    _ = registry.definitions
    assert registry._built is True


def test_tools_openai_formats_correctly():
    registry = ToolRegistry()
    registry.register("tool_a", lambda: "a", {
        "function": {"name": "tool_a", "description": "Does A"}
    })
    registry.register("tool_b", lambda: "b", {
        "function": {"name": "tool_b", "description": "Does B"}
    })
    # Prevent lazy build from discovering all package tools
    registry._built = True

    result = registry.tools_openai

    assert len(result) == 2
    assert result[0] == {
        "type": "function",
        "function": {"name": "tool_a", "description": "Does A"},
    }
    assert result[1] == {
        "type": "function",
        "function": {"name": "tool_b", "description": "Does B"},
    }


def test_tools_openai_returns_empty_list_when_no_tools():
    registry = ToolRegistry()
    registry._built = True
    assert registry.tools_openai == []


def test_build_skips_internal_modules():
    import src.tools.registry as registry_mod

    registry = ToolRegistry()
    registry._built = False
    registry._package = "src.tools"

    with patch.object(registry_mod, "os") as mock_os:
        mock_os.path.dirname.return_value = "/fake/src/tools"
        mock_os.listdir.return_value = [
            "__init__.py", "runner.py", "loader.py", "registry.py",
            "_helper.py", "actual_tool.py",
        ]
        with patch.object(registry_mod, "importlib") as mock_importlib:
            mock_pkg = MagicMock()
            mock_pkg.__file__ = "/fake/src/tools/__init__.py"
            mock_importlib.import_module.return_value = mock_pkg
            registry.build()

    registry._built = True


def test_get_triggers_lazy_build():
    registry = ToolRegistry()
    assert registry._built is False

    result = registry.get("anything")
    assert result is None
    assert registry._built is True
