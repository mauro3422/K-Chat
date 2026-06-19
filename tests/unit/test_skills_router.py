import pytest
from types import SimpleNamespace
from fastapi import APIRouter, HTTPException

from src.api.skills import SkillRegistry
from web.routers.skills import router, list_skills, get_skill


def _make_request(skill_registry: SkillRegistry | None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(skill_registry=skill_registry)))


@pytest.mark.anyio
async def test_skills_router_exists():
    assert isinstance(router, APIRouter)


@pytest.mark.anyio
async def test_skills_router_has_routes():
    paths = [r.path for r in router.routes]
    assert "/api/skills" in paths
    assert "/api/skills/{name}" in paths


@pytest.mark.anyio
async def test_list_skills_requires_initialized_registry():
    with pytest.raises(HTTPException) as exc:
        list_skills(_make_request(None))
    assert exc.value.status_code == 500


@pytest.mark.anyio
async def test_list_skills():
    skills = list_skills(_make_request(SkillRegistry()))
    assert isinstance(skills, list)
    for s in skills:
        assert s["name"] != "INDEX"
        assert s["name"] != "INDEX.md"
        assert "title" in s


@pytest.mark.anyio
async def test_get_skill_valid():
    skill = get_skill("html-widgets", _make_request(SkillRegistry()))
    assert skill["name"] == "html-widgets"
    assert "content" in skill
    assert "# Skill: Interactive HTML Widgets" in skill["content"]


@pytest.mark.anyio
async def test_get_skill_invalid():
    with pytest.raises(HTTPException) as exc:
        get_skill("", _make_request(SkillRegistry()))
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_get_skill_not_found():
    with pytest.raises(HTTPException) as exc:
        get_skill("non-existent-skill-name-xyz", _make_request(SkillRegistry()))
    assert exc.value.status_code == 404
