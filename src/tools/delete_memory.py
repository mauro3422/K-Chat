"""Tool: delete_memory — remove a memory entry from MEMORY.md + memory.db."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "delete_memory",
        "description": "Remove a memory entry by its key from MEMORY.md, memory.db, and vector embeddings.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The key of the memory to delete (e.g. 'test:nombre', 'user:ubicacion')."
                }
            },
            "required": ["key"]
        }
    }
}


async def run(**kwargs) -> str:
    key = kwargs.get("key", "").strip()
    if not key:
        return "[ERROR] key is required."
    from src.tools.save_memory import run as save_run
    call_kwargs = {k: v for k, v in kwargs.items() if k != "key"}
    return await save_run(key=key, value="", **call_kwargs)
