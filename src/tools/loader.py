import os
import logging
import importlib

logger = logging.getLogger(__name__)

# Filled once at module load time by single-threaded import, never mutated after — thread-safe
TOOL_MAP = {}
TOOL_DEFINITIONS = {}

_dir = os.path.dirname(__file__)
for f in sorted(os.listdir(_dir)):
    if not f.endswith('.py') or f.startswith('__') or f == 'runner.py':
        continue
    mod_name = f[:-3]
    try:
        mod = importlib.import_module(f'src.tools.{mod_name}')
        if not hasattr(mod, 'DEFINITION'):
            logger.warning("Tool %s: does not export DEFINITION, ignored", mod_name)
            continue
        if not hasattr(mod, 'run'):
            logger.warning("Tool %s: does not export run(), ignored", mod_name)
            continue
        tool_name = mod.DEFINITION['function']['name']
        TOOL_MAP[tool_name] = mod.run
        TOOL_DEFINITIONS[tool_name] = mod.DEFINITION
        logger.debug("Tool loaded into internal map: %s", mod_name)
    except Exception as e:
        logger.warning("Tool %s: error loading (%s), ignored", mod_name, e)
