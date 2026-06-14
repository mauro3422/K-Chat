"""Tools package public surface."""

from src.tools.registry import ToolRegistry
from src.tools.runner import run_parallel_tools

_DEFAULT_REGISTRY: ToolRegistry | None = None

def get_default_registry() -> ToolRegistry:
    """Get or create the default tool registry (lazy singleton)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ToolRegistry().discover().build()
    return _DEFAULT_REGISTRY

__all__ = [
    "run_parallel_tools",
    "get_default_registry",
    "ToolRegistry",
]
