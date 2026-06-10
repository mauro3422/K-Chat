from src.tools.loader import TOOL_MAP as TOOL_MAP, TOOL_DEFINITIONS
from src.tools.runner import run_parallel_tools as run_parallel_tools

# Built once at import time, immutable after — thread-safe by single-threaded import
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_action",
            "description": "Executes a specialized system action (web search, file read/write, persistent memory, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_name": {
                        "type": "string",
                        "description": "The name of the action to execute. Valid actions: " + ', '.join(f"'{k}'" for k in sorted(TOOL_DEFINITIONS.keys())) + "."
                    },
                    "arguments": {
                        "type": "object",
                        "description": "The arguments for the specified action as a key-value dictionary (e.g. {'query': 'weather'} for web_search or {'path': 'README.md'} for read_file)."
                    }
                },
                "required": ["action_name", "arguments"]
            }
        }
    }
]
