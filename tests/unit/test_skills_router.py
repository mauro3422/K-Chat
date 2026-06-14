import pytest
from fastapi import APIRouter, HTTPException
from web.routers.skills import router, list_skills, get_skill

@pytest.mark.anyio
async def test_skills_router_exists():
    assert isinstance(router, APIRouter)

@pytest.mark.anyio
async def test_skills_router_has_routes():
    paths = [r.path for r in router.routes]
    assert "/api/skills" in paths
    assert "/api/skills/{name}" in paths

@pytest.mark.anyio
async def test_list_skills():
    skills = list_skills()
    assert isinstance(skills, list)
    # INDEX.md should not be in the list
    for s in skills:
        assert s["name"] != "INDEX"
        assert s["name"] != "INDEX.md"
        assert "title" in s

@pytest.mark.anyio
async def test_get_skill_valid():
    # html-widgets should exist in the skills directory
    skill = get_skill("html-widgets")
    assert skill["name"] == "html-widgets"
    assert "content" in skill
    assert "# Skill: Interactive HTML Widgets" in skill["content"]

@pytest.mark.anyio
async def test_get_skill_invalid():
    with pytest.raises(HTTPException) as exc:
        get_skill("")
    assert exc.value.status_code == 400

@pytest.mark.anyio
async def test_get_skill_not_found():
    with pytest.raises(HTTPException) as exc:
        get_skill("non-existent-skill-name-xyz")
    assert exc.value.status_code == 404
