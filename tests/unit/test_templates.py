from unittest.mock import patch


def test_templates_dict_has_keys():
    from src.context.templates import TEMPLATES

    assert "SOUL.md" in TEMPLATES
    assert "MEMORY.md" in TEMPLATES
    assert "AGENTS.md" in TEMPLATES


def test_soul_template_contains_kairos():
    from src.context.templates import TEMPLATES

    assert "Kairos" in TEMPLATES["SOUL.md"]


def test_memory_template_contains_user_name():
    from src.context.templates import TEMPLATES

    assert "User:" in TEMPLATES["MEMORY.md"]


def test_agents_template_contains_agent_rules():
    from src.context.templates import TEMPLATES

    assert "Agent rules" in TEMPLATES["AGENTS.md"]
