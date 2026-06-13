"""Tools package public surface."""

from src.tools.registry import ToolRegistry
from src.tools.runner import run_parallel_tools

_DEFAULT_REGISTRY: ToolRegistry | None = None

# Module-level dicts used by the default registry and tests.
TOOL_MAP: dict = {}
TOOL_DEFINITIONS: dict = {}
TOOLS: list = []


def get_default_registry() -> ToolRegistry:
    """Get or create the default tool registry (lazy singleton)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ToolRegistry().discover().build()
        global TOOLS
        TOOLS = _DEFAULT_REGISTRY.tools_openai
    return _DEFAULT_REGISTRY

__all__ = [
    "TOOL_MAP",
    "TOOL_DEFINITIONS",
    "TOOLS",
    "run_parallel_tools",
    "get_default_registry",
    "ToolRegistry",
]
