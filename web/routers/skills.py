import logging
from typing import Any
from fastapi import APIRouter, HTTPException

from src.skills import SkillRegistry

logger = logging.getLogger(__name__)
router = APIRouter()
registry = SkillRegistry()


@router.get("/api/skills")
def list_skills() -> list[dict[str, str]]:
    try:
        return registry.discover().list_skills()
    except Exception as e:
        logger.exception("Failed to list skills: %s", e)
        raise HTTPException(status_code=500, detail="Could not read skills directory.")


@router.get("/api/skills/{name}")
def get_skill(name: str) -> dict[str, Any]:
    if not name or not "".join(c for c in name if c.isalnum() or c in ("-", "_")):
        raise HTTPException(status_code=400, detail="Invalid skill name.")
    try:
        skill = registry.discover().get_skill(name)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found.")
        return {"name": skill["name"], "content": skill["content"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to read skill %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Could not read skill file.")
