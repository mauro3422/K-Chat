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
                    "description": "Entity ID or entity name to start exploration from."
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
    entity_query = kwargs.get("entity_id", "").strip()
    depth = min(kwargs.get("depth", 2), 5)
    _repos = kwargs.get("_repos")

    if not entity_query:
        return "[ERROR] entity_id cannot be empty."

    try:
        repo = _repos.memory.entity_graph if _repos else None
        entity_id = entity_query
        entity = None
        if repo is not None:
            entity = await repo.get_entity(entity_query)
            if entity is None:
                matches = await repo.search_entities(entity_query, limit=6)
                exact = [
                    item
                    for item in matches
                    if str(item.get("name", "")).casefold() == entity_query.casefold()
                ]
                candidates = exact or matches
                if len(candidates) == 1:
                    entity = candidates[0]
                    entity_id = str(entity["id"])
                elif len(candidates) > 1:
                    options = ", ".join(
                        f"{item.get('name', '?')} ({item.get('id', '?')})"
                        for item in candidates[:5]
                    )
                    return (
                        f"Nombre ambiguo '{entity_query}'. "
                        f"Usá uno de estos IDs: {options}"
                    )

        if repo is None:
            from src.memory.entity.linker import explore_graph as _eg
            results = await _eg(entity_id, depth=depth)
        else:
            results = await repo.explore_graph(entity_id, depth=depth)

        if not results:
            # Try to get the entity itself
            if repo and entity is None:
                entity = await repo.get_entity(entity_id)
            if isinstance(entity, dict):
                return f"Entidad '{entity.get('name', '?')}' encontrada pero sin conexiones."
            return f"No se encontró la entidad '{entity_query}'."

        statistical = [
            item
            for item in results
            if str(item.get("relation_type", "")).casefold() == "co_occurrence"
        ]
        semantic = [item for item in results if item not in statistical]
        if semantic:
            results = semantic

        # Group by depth
        by_depth: dict[int, list] = {}
        for r in results:
            d = r.get("depth", 0)
            by_depth.setdefault(d, []).append(r)

        lines = [f"🕸️ **Graph Explorer** (depth {depth})\n"]
        root_name = (
            str(entity.get("name") or entity_query)
            if isinstance(entity, dict)
            else entity_query
        )
        for d in sorted(by_depth.keys()):
            items = by_depth[d]
            icon = {1: "→", 2: "↳", 3: "  ↳", 4: "    ↳", 5: "      ↳"}.get(d, "  •")
            for item in items[:10]:  # limit per depth
                name = item.get("name", "?")
                etype = item.get("entity_type", "?")
                rel = item.get("relation_type", "") or ""
                rel_str = f" [{rel}]" if rel else ""
                source_id = str(item.get("source_id", ""))
                target_id = str(item.get("target_id", ""))
                if d == 1 and rel and source_id == entity_id:
                    relation_view = f" — {root_name} -[{rel}]→ {name}"
                elif d == 1 and rel and target_id == entity_id:
                    relation_view = f" — {name} -[{rel}]→ {root_name}"
                else:
                    relation_view = rel_str
                lines.append(f"{icon} **{name}** ({etype}){relation_view}")
            if len(items) > 10:
                lines.append(f"{icon} ... y {len(items) - 10} más")
        if semantic and statistical:
            lines.append(
                f"\n_Se omitieron {len(statistical)} conexiones estadísticas "
                "`co_occurrence` para priorizar relaciones semánticas._"
            )

        return "\n".join(lines)
    except Exception as e:
        logger.exception("explore_graph failed")
        return f"[ERROR] {e}"
