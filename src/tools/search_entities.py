"""Tool: search_entities — search the entity knowledge graph."""
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_entities",
        "description": "Search the entity knowledge graph for people, projects, technologies, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Entity name or keyword to search for."
                },
                "entity_type": {
                    "type": "string",
                    "enum": ["", "persona", "proyecto", "tecnologia", "lenguaje", "tema", "lugar"],
                    "description": "Filter by entity type (optional).",
                    "default": ""
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 10, max: 50).",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    }
}

async def run(**kwargs) -> str:
    query = kwargs.get("query", "").strip()
    entity_type = kwargs.get("entity_type", "") or None
    limit = min(kwargs.get("limit", 10), 50)
    _repos = kwargs.get("_repos")

    if not query:
        return "[ERROR] query cannot be empty."

    try:
        # Use injected repo from DI
        repo = _repos.memory.entity_graph if _repos else None
        if repo is None:
            # Fallback: use the module-level function
            from src.memory.entity.linker import search_entities as _se
            results = await _se(query, entity_type=entity_type, limit=limit)
        else:
            results = await repo.search_entities(query, entity_type=entity_type, limit=limit)

        if not results:
            return f"No se encontraron entidades para \"{query}\"."

        lines = [f"🔍 **Entidades encontradas para \"{query}\"**\n"]
        for r in results:
            icon = {"persona": "👤", "proyecto": "📦", "tecnologia": "🔧", "lenguaje": "💻", "tema": "📋", "lugar": "📍"}.get(r.get("entity_type", ""), "❓")
            name = r.get("name", "?")
            etype = r.get("entity_type", "?")
            count = r.get("mention_count", 0)
            last_seen = r.get("last_seen", "")[:10]
            lines.append(f"{icon} **{name}** ({etype}) — {count} menciones, última: {last_seen}")

        return "\n".join(lines)
    except Exception as e:
        logger.exception("search_entities failed")
        return f"[ERROR] {e}"
