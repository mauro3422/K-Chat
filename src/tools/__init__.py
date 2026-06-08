import os
import logging
import importlib

logger = logging.getLogger(__name__)

TOOLS = []
TOOL_MAP = {}

_dir = os.path.dirname(__file__)
for f in sorted(os.listdir(_dir)):
    if not f.endswith('.py') or f.startswith('__'):
        continue
    mod_name = f[:-3]
    try:
        mod = importlib.import_module(f'src.tools.{mod_name}')
        if not hasattr(mod, 'DEFINITION'):
            logger.warning("Tool %s: no exporta DEFINITION, ignorada", mod_name)
            continue
        if not hasattr(mod, 'run'):
            logger.warning("Tool %s: no exporta run(), ignorada", mod_name)
            continue
        TOOLS.append(mod.DEFINITION)
        TOOL_MAP[mod.DEFINITION['function']['name']] = mod.run
        logger.debug("Tool cargada: %s", mod_name)
    except Exception as e:
        logger.warning("Tool %s: error al cargar (%s), ignorada", mod_name, e)
