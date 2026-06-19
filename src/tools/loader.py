# DEPRECATED: This module is only used by tests (tests/unit/test_tool_loader.py).
# Production code uses src.tools.get_default_registry() and src.tools.ToolRegistry
# (src/tools/__init__.py and src/tools/registry.py) instead.
# Do not add new runtime imports here.
import os
import logging
import importlib
from typing import Any, Callable

logger: logging.Logger = logging.getLogger(__name__)

# Filled once at module load time by single-threaded import, never mutated after — thread-safe
TOOL_MAP: dict[str, Callable[..., str]] = {}
TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {}

_dir: str = os.path.dirname(__file__)
for f in sorted(os.listdir(_dir)):
    if not f.endswith('.py') or f.startswith('_') or f in ('runner.py', 'loader.py'):
        continue
    mod_name: str = f[:-3]
    try:
        mod = importlib.import_module(f'src.tools.{mod_name}')
        if not hasattr(mod, 'DEFINITION'):
            logger.warning("Tool %s: does not export DEFINITION, ignored", mod_name)
            continue
        if not hasattr(mod, 'run'):
            logger.warning("Tool %s: does not export run(), ignored", mod_name)
            continue
        tool_name: str = mod.DEFINITION['function']['name']
        TOOL_MAP[tool_name] = mod.run
        TOOL_DEFINITIONS[tool_name] = mod.DEFINITION
        logger.debug("Tool loaded into internal map: %s", mod_name)
    except Exception as e:
        logger.warning("Tool %s: error loading (%s), ignored", mod_name, e)
