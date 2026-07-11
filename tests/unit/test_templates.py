import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch


@pytest.mark.anyio
async def test_templates_dict_has_keys():
    from src.context.templates import get_templates
    templates = get_templates()

    assert "SOUL.md" in templates
    assert "MEMORY.md" in templates
    assert "AGENTS.md" in templates


@pytest.mark.anyio
async def test_soul_template_contains_kairos():
    from src.context.templates import get_templates

    assert "Kairos" in get_templates()["SOUL.md"]


@pytest.mark.anyio
async def test_memory_template_contains_user_name():
    from src.context.templates import get_templates

    assert "User:" in get_templates()["MEMORY.md"]


@pytest.mark.anyio
async def test_agents_template_contains_agent_rules():
    from src.context.templates import get_templates

    assert "Agent rules" in get_templates()["AGENTS.md"]
