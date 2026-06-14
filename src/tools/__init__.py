"""Tools package public surface."""

from typing import Any
from src.tools.registry import ToolRegistry
from src.tools.runner import run_parallel_tools


def build_default_registry(skill_registry: Any | None = None) -> ToolRegistry:
    """Build a fresh tool registry (not cached, no singleton).

    *skill_registry* — optional SkillRegistry instance. When omitted,
    a default ``SkillRegistry()`` is created.
    """
    if skill_registry is None:
        from src.skills.registry import SkillRegistry
        skill_registry = SkillRegistry()
    return ToolRegistry().discover().build(skill_registry=skill_registry)


# Backward-compat alias — deprecated, prefer build_default_registry() or DI.
get_default_registry = build_default_registry

__all__ = [
    "run_parallel_tools",
    "build_default_registry",
    "get_default_registry",
    "ToolRegistry",
]
