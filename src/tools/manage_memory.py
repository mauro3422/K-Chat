"""Tool: manage_memory — maintenance operations for the memory system.

Operations:
- reindex: Regenera embeddings de todas las entradas de MEMORY.md
- reindex_sessions: Vectoriza exchanges de sesiones (con filtro por valor)
- reindex_session <id>: Vectoriza una sesion especifica
- clusters: Muestra los topic clusters existentes
- topics: Muestra el mapa de relaciones entre temas
- stats: Muestra estadisticas del sistema de memoria
- compare: Compara MEMORY.md vs memory.db (opcional filter por key_pattern)
- repair: Corrige inconsistencias entre MEMORY.md y memory.db
- sync: Sincroniza memory.db desde MEMORY.md
- find: Busca texto en MEMORY.md
- export: Exporta MEMORY.md a JSON

DI: recibe ``_repos.memory`` (MemoryRepositories) con memory_index + vector_store.
"""

from typing import Any

from src.memory.operations.reindex import (
    _reindex_memories,
    _reindex_sessions,
    _reindex_single_session,
)
from src.memory.operations.sync import _compare, _repair, _sync
from src.memory.operations.query import (
    _export,
    _find,
    _memory_stats,
    _show_clusters,
    _show_topics,
)
from src.memory.operations.archive import _archive
from src.tools.save_memory import run as _save_run

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "manage_memory",
        "description": "Maintenance operations for the memory system. "
                       "Use 'reindex' to regenerate embeddings for MEMORY.md entries. "
                       "Use 'reindex_sessions' to vectorize session exchanges. "
                       "Use 'reindex_session <id>' for a single session. "
                       "Use 'clusters' to see topic clusters. "
                       "Use 'topics' to see the topic map. "
                       "Use 'stats' to see memory system status. "
                       "Use 'compare' to compare MEMORY.md vs memory.db. "
                       "Use 'repair' to fix inconsistencies. "
                       "Use 'sync' to sync memory.db from MEMORY.md. "
                       "Use 'archive' to archive entries (prefix key with _archived:). "
                       "Use 'find' to search in MEMORY.md. "
                       "Use 'export' to export as JSON.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["reindex", "reindex_sessions", "reindex_session",
                             "clusters", "topics", "stats",
                             "compare", "repair", "sync", "archive",
                             "find", "export"],
                    "description": "Operation to perform."
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID for reindex_session (optional)."
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only count/show (default: False).",
                    "default": False
                },
                "confirm": {
                    "type": "boolean",
                    "description": "If True, confirm destructive operations (default: False).",
                    "default": False
                },
                "key_pattern": {
                    "type": "string",
                    "description": "Filter by key pattern (e.g. 'user:*', 'bug:*'). Supports * wildcard.",
                    "default": ""
                },
                "find_text": {
                    "type": "string",
                    "description": "Text to search for (used with 'find').",
                    "default": ""
                },
                "fmt": {
                    "type": "string",
                    "enum": ["text", "json"],
                    "description": "Output format (default: text).",
                    "default": "text"
                }
            },
            "required": ["operation"]
        }
    }
}


async def run(**kwargs) -> str:
    operation = kwargs.get("operation", "")
    session_id = kwargs.get("session_id", "")
    dry_run = kwargs.get("dry_run", False)
    confirm = kwargs.get("confirm", False)
    key_pattern = kwargs.get("key_pattern", "")
    find_text = kwargs.get("find_text", "")
    fmt = kwargs.get("fmt", "text")
    _repos = kwargs.get("_repos")

    if operation == "reindex":
        return await _reindex_memories(dry_run=dry_run, repos=_repos)
    elif operation == "reindex_sessions":
        return await _reindex_sessions(dry_run=dry_run, repos=_repos)
    elif operation == "reindex_session":
        if not session_id:
            return "[ERROR] Se requiere session_id para reindex_session."
        return await _reindex_single_session(session_id, dry_run=dry_run, repos=_repos)
    elif operation == "clusters":
        return await _show_clusters(repos=_repos)
    elif operation == "topics":
        return await _show_topics(repos=_repos)
    elif operation == "stats":
        return await _memory_stats(repos=_repos)
    elif operation == "compare":
        return await _compare(key_pattern=key_pattern, fmt=fmt, repos=_repos)
    elif operation == "repair":
        return await _repair(dry_run=dry_run, confirm=confirm, repos=_repos)
    elif operation == "sync":
        return await _sync(dry_run=dry_run, confirm=confirm, repos=_repos)
    elif operation == "find":
        if not find_text:
            return "[ERROR] find requiere find_text."
        return await _find(find_text=find_text, repos=_repos)
    elif operation == "archive":
        return await _archive(
            key_pattern=key_pattern,
            dry_run=dry_run,
            confirm=confirm,
            repos=_repos,
            save_memory_fn=lambda k, v: _save_run(key=k, value=v, _repos=_repos),
        )
    elif operation == "export":
        return await _export(fmt=fmt, repos=_repos)
    else:
        return f"[ERROR] Operacion desconocida: {operation}"
