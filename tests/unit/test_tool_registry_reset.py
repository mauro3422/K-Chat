from src.tools.registry import ToolRegistry


def test_tool_registry_reset_clears_build_state():
    registry = ToolRegistry()
    registry.discover("src.tools").build()
    assert registry._built
    registry.reset()
    assert not registry._built
    assert registry._tool_map == {}
    assert registry._definitions == {}
