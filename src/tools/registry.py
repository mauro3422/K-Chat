"""ToolRegistry - Immutable tool registry with lazy discovery and build pattern."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import importlib
import importlib.util
import os
import logging

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolRegistry:
    """Immutable tool registry supporting lazy discovery and explicit build."""
    
    _tool_map: dict[str, Callable[..., str]] = field(default_factory=dict, init=False)
    _definitions: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _built: bool = field(default=False, init=False)
    _package: str = field(default="src.tools", init=False)
    
    def discover(self, package: str = "src.tools") -> "ToolRegistry":
        """Discover tools from package without building. Returns self for chaining."""
        if self._built:
            logger.warning("Registry already built, discover() has no effect")
            return self
        self._package = package
        return self
    
    def register(self, name: str, run_fn: Callable[..., str], definition: dict[str, Any]) -> "ToolRegistry":
        """Manually register a tool. Returns self for chaining."""
        if self._built:
            raise RuntimeError("Cannot register tools after build()")
        self._tool_map[name] = run_fn
        self._definitions[name] = definition
        return self
    
    def build(self) -> "ToolRegistry":
        """Build registry by discovering tools from package. Returns self for chaining."""
        if self._built:
            return self
        
        # Discover tools from package
        try:
            pkg_dir = os.path.dirname(importlib.import_module(self._package).__file__ or "")
        except Exception as e:
            logger.warning("Could not locate package %s: %s", self._package, e)
            self._built = True
            return self
        
        for f in sorted(os.listdir(pkg_dir)):
            if not f.endswith('.py') or f.startswith('_') or f in ('runner.py', 'loader.py', 'registry.py'):
                continue
            mod_name: str = f[:-3]
            try:
                mod = importlib.import_module(f'{self._package}.{mod_name}')
                if not hasattr(mod, 'DEFINITION'):
                    logger.warning("Tool %s: does not export DEFINITION, ignored", mod_name)
                    continue
                if not hasattr(mod, 'run'):
                    logger.warning("Tool %s: does not export run(), ignored", mod_name)
                    continue
                tool_name: str = mod.DEFINITION['function']['name']
                self._tool_map[tool_name] = mod.run
                self._definitions[tool_name] = mod.DEFINITION
                logger.debug("Tool loaded into registry: %s", mod_name)
            except Exception as e:
                logger.warning("Tool %s: error loading (%s), ignored", mod_name, e)
        
        
        # Discover tools from skills directory
        try:
            from src.skills.registry import SkillRegistry
            for tool_name, (run_fn, definition) in SkillRegistry().discover_tools().items():
                self._tool_map[tool_name] = run_fn
                self._definitions[tool_name] = definition
        except Exception as e:
            logger.warning("Error scanning skills folder for tools via SkillRegistry: %s", e)

        self._built = True
        return self
    
    @property
    def tool_map(self) -> dict[str, Callable[..., str]]:
        """Get tool map (triggers lazy build if needed)."""
        if not self._built:
            self.build()
        return self._tool_map
    
    @property
    def definitions(self) -> dict[str, dict[str, Any]]:
        """Get tool definitions (triggers lazy build if needed)."""
        if not self._built:
            self.build()
        return self._definitions
    
    @property
    def tools_openai(self) -> list[dict[str, Any]]:
        """Get OpenAI-format tool definitions (triggers lazy build if needed)."""
        if not self._built:
            self.build()
        definitions = self._definitions
        return [
            {"type": "function", "function": {**definitions[name]["function"]}}
            for name in sorted(definitions.keys())
        ]
    
    def get(self, name: str) -> Callable[..., str] | None:
        """Get a single tool by name (triggers lazy build if needed)."""
        if not self._built:
            self.build()
        return self._tool_map.get(name)
