"""Tool to list all entries in the curated memory.db.

Shows all saved memory entries grouped by category prefix
or filtered by a key prefix. This is the structured counterpart
of MEMORY.md.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_memories",
        "description": "Lista las entradas guardadas en memoria (memory.db). Puede filtrar por prefijo de key (ej: 'user:', 'bug:', 'proyecto:'). Si no se especifica filtro, muestra todas agrupadas por categoría.",
        "parameters": {
            "type": "object",
            "properties": {
                "prefix": {
                    "type": "string",
                    "description": "Filtrar por prefijo de key (ej: 'user:', 'bug:', 'proyecto:', 'arquitectura:'). Vacío = todas.",
                    "default": ""
                }
            },
            "required": []
        }
    }
}


async def run(**kwargs) -> str:
    prefix = (kwargs.get("prefix") or "").strip()
    _repos = kwargs.get("_repos")

    if _repos is None or _repos.memory is None:
        return "[ERROR] Sistema de memoria no disponible."

    try:
        all_entries = await _repos.memory.memory_index.get_all()
    except Exception as e:
        logger.exception("list_memories failed")
        return f"[ERROR] Error al leer memoria: {e}"

    if not all_entries:
        return "[OK] No hay entradas en memoria todavía."

    # Filter by prefix if specified
    if prefix:
        filtered = [e for e in all_entries if e.get("key", "").startswith(prefix)]
    else:
        filtered = all_entries

    if not filtered:
        if prefix:
            return f"[OK] No se encontraron entradas con prefijo '{prefix}'."
        return "[OK] No hay entradas en memoria."

    # Group by category (first part of key before ':')
    groups: dict[str, list[dict]] = {}
    for entry in filtered:
        key = entry.get("key", "?")
        cat = key.split(":")[0] if ":" in key else "other"
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(entry)

    lines = [f"📖 **{len(filtered)} entradas** en memoria"]
    if prefix:
        lines[0] += f" (filtro: '{prefix}')"
    lines.append("")

    for cat in sorted(groups.keys()):
        entries = groups[cat]
        lines.append(f"  **{cat}** ({len(entries)}):")
        for e in entries:
            key = e.get("key", "?")
            value = e.get("value", "?")
            # Truncate value if too long
            if len(value) > 100:
                value = value[:97] + "..."
            lines.append(f"    • `{key}` → {value}")
        lines.append("")

    return "\n".join(lines)
