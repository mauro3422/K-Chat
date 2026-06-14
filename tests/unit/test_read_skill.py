import pytest
from unittest.mock import AsyncMock

from src.skills import SkillRegistry
from src.tools.read_skill import run as read_skill_run

_skill_registry = SkillRegistry()


@pytest.mark.anyio
async def test_read_skill_success():
    """Verify that read_skill retrieves existing skill files correctly."""
    # The html-widgets skill should exist
    res = read_skill_run("html-widgets", _skill_registry=_skill_registry)
    assert "[ERROR]" not in res
    assert "Skill: Interactive HTML Widgets" in res
    assert "html-widget" in res


@pytest.mark.anyio
async def test_read_skill_not_found():
    """Verify that read_skill returns an error and a list of available skills when a skill is missing."""
    res = read_skill_run("non-existent-skill-xyz", _skill_registry=_skill_registry)
    assert "[ERROR]" in res
    assert "non-existent-skill-xyz" in res
    assert "html-widgets" in res  # lists html-widgets as available


@pytest.mark.anyio
async def test_read_skill_sanitization():
    """Verify that read_skill prevents directory traversal attacks and invalid names."""
    # Directory traversal
    res = read_skill_run("../../etc/passwd", _skill_registry=_skill_registry)
    # Sanitized to 'etcpasswd', which won't exist
    assert "[ERROR]" in res
    assert "etcpasswd" in res

    # Empty name
    res2 = read_skill_run("...///...", _skill_registry=_skill_registry)
    assert "[ERROR]" in res2
    assert "Invalid skill name" in res2
