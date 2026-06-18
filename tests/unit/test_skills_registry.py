import os
import pytest
from src.skills.registry import SkillRegistry

@pytest.mark.anyio
async def test_skill_registry_discovery():
    registry = SkillRegistry()
    registry.discover()
    assert registry._built
    skills = registry.list_skills()
    assert isinstance(skills, list)
    assert len(skills) >= 2
    names = [s["name"] for s in skills]
    assert "db-query" in names
    assert "html-widgets" in names

@pytest.mark.anyio
async def test_skill_registry_discover_tools():
    registry = SkillRegistry()
    tools = registry.discover_tools()
    assert isinstance(tools, dict)
    assert "db_query" in tools
    run_fn, definition = tools["db_query"]
    assert callable(run_fn)
    assert definition["function"]["name"] == "db_query"


@pytest.mark.anyio
async def test_skill_registry_reset_allows_rediscovery():
    registry = SkillRegistry()
    registry.discover()
    assert registry._built
    registry.reset()
    assert not registry._built
