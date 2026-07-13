"""Tools package public surface."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "run_parallel_tools",
    "build_default_registry",
    "get_default_registry",
    "ToolRegistry",
]


def _load_tool_registry_class():
    return import_module("src.tools.registry").ToolRegistry


def _load_run_parallel_tools():
    return import_module("src.tools.runner").run_parallel_tools


def __getattr__(name: str):
    if name == "ToolRegistry":
        value = _load_tool_registry_class()
    elif name == "run_parallel_tools":
        value = _load_run_parallel_tools()
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def build_default_registry(skill_registry: Any | None = None):
    """Build a fresh tool registry (not cached, no singleton).

    *skill_registry* - optional SkillRegistry instance. When omitted,
    a default ``SkillRegistry()`` is created.
    """
    ToolRegistry = _load_tool_registry_class()
    if skill_registry is None:
        from src.skills.registry import SkillRegistry

        skill_registry = SkillRegistry()
    return ToolRegistry().discover().build(skill_registry=skill_registry)


# Backward-compat alias - deprecated, prefer build_default_registry() or DI.
get_default_registry = build_default_registry
