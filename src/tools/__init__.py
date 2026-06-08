import os, importlib

TOOLS = []
TOOL_MAP = {}

_dir = os.path.dirname(__file__)
for f in sorted(os.listdir(_dir)):
    if not f.endswith('.py') or f.startswith('__'):
        continue
    mod = importlib.import_module(f'src.tools.{f[:-3]}')
    if not hasattr(mod, 'DEFINITION'):
        raise AttributeError(f"{f} no exporta DEFINITION")
    if not hasattr(mod, 'run'):
        raise AttributeError(f"{f} no exporta run()")
    TOOLS.append(mod.DEFINITION)
    TOOL_MAP[mod.DEFINITION['function']['name']] = mod.run
