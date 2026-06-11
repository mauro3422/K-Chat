from src.tools.loader import TOOL_MAP as TOOL_MAP, TOOL_DEFINITIONS
from src.tools.runner import run_parallel_tools as run_parallel_tools

# Built once at import time, immutable after — thread-safe by single-threaded import
TOOLS = [
    {"type": "function", "function": {**TOOL_DEFINITIONS[name]["function"]}}
    for name in sorted(TOOL_DEFINITIONS.keys())
]
