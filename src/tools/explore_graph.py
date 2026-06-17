"""Tool: explore_graph — traverse the entity knowledge graph."""
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "explore_graph",
        "description": "Explore the entity relationship graph from a starting entity. Shows connected entities up to N depth.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Entity ID to start exploration from."
                },
                "depth": {
                    "type": "integer",
                    "description": "How many levels deep to explore (default: 2, max: 5).",
                    "default": 2
                }
            },
            "required": ["entity_id"]
        }
    }
}

async def run(**kwargs) -> str:
    entity_id = kwargs.get("entity_id", "").strip()
    depth = min(kwargs.get("depth", 2), 5)
    _repos = kwargs.get("_repos")

    if not entity_id:
        return "[ERROR] entity_id cannot be empty."

    try:
        repo = _repos.memory.entity_graph if _repos else None
        if repo is None:
            from src.memory.entity.linker import explore_graph as _eg
            results = await _eg(entity_id, depth=depth)
        else:
            results = await repo.explore_graph(entity_id, depth=depth)

        if not results:
            # Try to get the entity itself
            if repo:
                entity = await repo.get_entity(entity_id)
            else:
                entity = None
            if entity:
                return f"Entidad '{entity.get('name', '?')}' encontrada pero sin conexiones."
            return f"No se encontró la entidad {entity_id[:16]}..."

        # Group by depth
        by_depth: dict[int, list] = {}
        for r in results:
            d = r.get("depth", 0)
            by_depth.setdefault(d, []).append(r)

        lines = [f"🕸️ **Graph Explorer** (depth {depth})\n"]
        for d in sorted(by_depth.keys()):
            items = by_depth[d]
            icon = {1: "→", 2: "↳", 3: "  ↳", 4: "    ↳", 5: "      ↳"}.get(d, "  •")
            for item in items[:10]:  # limit per depth
                name = item.get("name", "?")
                etype = item.get("entity_type", "?")
                rel = item.get("relation_type", "") or ""
                rel_str = f" [{rel}]" if rel else ""
                lines.append(f"{icon} **{name}** ({etype}){rel_str}")
            if len(items) > 10:
                lines.append(f"{icon} ... y {len(items) - 10} más")

        return "\n".join(lines)
    except Exception as e:
        logger.exception("explore_graph failed")
        return f"[ERROR] {e}"
