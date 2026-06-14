"""Tools package public surface."""

from src.tools.registry import ToolRegistry
from src.tools.runner import run_parallel_tools


def build_default_registry() -> ToolRegistry:
    """Build a fresh tool registry (not cached, no singleton)."""
    from src.skills.registry import SkillRegistry
    return ToolRegistry().discover().build(skill_registry=SkillRegistry())


# Backward-compat alias — deprecated, prefer build_default_registry() or DI.
get_default_registry = build_default_registry

__all__ = [
    "run_parallel_tools",
    "build_default_registry",
    "get_default_registry",
    "ToolRegistry",
]
