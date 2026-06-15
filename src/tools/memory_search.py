"""Tool to search the curated memory.db by text query.

Queries the global memory_index for entries matching a search string
in either the key or value fields. This is the structured counterpart
of MEMORY.md.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "memory_search",
        "description": "Busca en la memoria curada (memory.db) entradas que coincidan con un texto. Sirve para encontrar información guardada sobre el usuario, proyectos, preferencias, etc. Útil cuando no recordás exactamente qué se guardó.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto a buscar en las memorias (busca en key y value)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de resultados a retornar (default: 20, max: 50).",
                    "default": 20
                }
            },
            "required": ["query"]
        }
    }
}


async def run(**kwargs) -> str:
    query = (kwargs.get("query") or "").strip()
    _repos = kwargs.get("_repos")
    limit = min(int(kwargs.get("limit", 20)), 50)

    if not query:
        return "[ERROR] La búsqueda no puede estar vacía."

    if _repos is None or _repos.memory is None:
        return "[ERROR] Sistema de memoria no disponible."

    try:
        results = await _repos.memory.memory_index.search(query)
    except Exception as e:
        logger.exception("memory_search failed")
        return f"[ERROR] Error al buscar en memoria: {e}"

    if not results:
        return f"[OK] No se encontraron entradas en memoria para '{query}'."

    # Apply limit
    results = results[:limit]

    lines = [f"📖 **{len(results)} resultados** para '{query}':", ""]
    for r in results:
        key = r.get("key", "?")
        value = r.get("value", "?")
        updated = r.get("updated_at", "")
        date_str = f" ({updated})" if updated else ""
        lines.append(f"- **{key}**: {value}{date_str}")

    return "\n".join(lines)
