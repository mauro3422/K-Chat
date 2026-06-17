from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from src.memory.operations._helpers import (
    _get_memory_md_path,
    _memory_db,
    _parse_memory_md,
    _sessions_db,
)

logger = logging.getLogger(__name__)


async def _show_clusters(repos: Any = None) -> str:
    try:
        with _memory_db(repos) as conn:
            clusters = conn.execute("""
                SELECT cluster_id, label, keywords, session_count, exchange_count,
                       first_seen, last_updated, weight
                FROM topic_clusters
                ORDER BY exchange_count DESC
                LIMIT 30
            """).fetchall()
    except sqlite3.OperationalError:
        return "No hay clusters todavia (tabla no existe)."

    if not clusters:
        return "No hay clusters todavia."

    lines = [f"Topic Clusters ({len(clusters)}):\n"]
    for c in clusters:
        kw = json.loads(c[2]) if c[2] else []
        kw_str = ", ".join(k["word"] for k in kw[:5])
        name = c[1] or kw_str
        lines.append(f"  - {name} ({c[4]} exchanges, {c[3]} sesiones, peso {c[7]})")
    return "\n".join(lines)


async def _show_topics(repos: Any = None) -> str:
    try:
        with _memory_db(repos) as conn:
            relations = conn.execute("""
                SELECT source_id, target_id, shared_keywords, shared_count,
                       relationship_type, weight
                FROM topic_relations
                ORDER BY weight DESC
                LIMIT 30
            """).fetchall()
    except sqlite3.OperationalError:
        return "No hay relaciones todavia (tabla no existe)."
    if not relations:
        return "No hay relaciones todavia."

    lines = [f"Topic Relations ({len(relations)}):\n"]
    for r in relations:
        kw = json.loads(r[2]) if r[2] else []
        kw_str = ", ".join(kw[:3])
        lines.append(f"  {r[0]} <-> {r[1]} ({r[4]}, peso {r[5]}) [{kw_str}]")
    return "\n".join(lines)


async def _memory_stats(repos: Any = None) -> str:
    """Show memory system stats."""
    with _sessions_db(repos) as sdb:
        s_total = sdb.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        s_with = sdb.execute(
            "SELECT COUNT(*) FROM sessions s WHERE EXISTS "
            "(SELECT 1 FROM messages m WHERE m.session_id = s.session_id)"
        ).fetchone()[0]
        msg_count = sdb.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        user_msgs = sdb.execute(
            "SELECT COUNT(*) FROM messages WHERE role='user' AND LENGTH(content)>20"
        ).fetchone()[0]

    mem = repos.memory if repos else None
    mem_count = await mem.memory_index.count() if mem else 0

    store = mem.vector_store if mem else None
    if store:
        vec_total = store.count()
        vec_mem = store.count(source="memory")
        vec_ses = store.count(source="session")
    else:
        vec_total = vec_mem = vec_ses = 0

    with _memory_db(repos) as conn:
        try:
            cluster_count = conn.execute("SELECT COUNT(*) FROM topic_clusters").fetchone()[0]
            rel_count = conn.execute("SELECT COUNT(*) FROM topic_relations").fetchone()[0]
        except sqlite3.OperationalError:
            cluster_count = 0
            rel_count = 0

    lines = [
        "MEMORY SYSTEM STATS",
        "",
        f"Sessions DB: {s_total} sesiones ({s_with} con mensajes)",
        f"  Mensajes: {msg_count} ({user_msgs} de usuario)",
        f"Memory DB: {mem_count} entradas",
        f"Vector Store: {vec_total} total ({vec_mem} memoria, {vec_ses} sesiones)",
        f"Clusters: {cluster_count} | Relaciones: {rel_count}",
        "",
        "Comandos: stats | reindex | reindex_sessions | clusters | topics",
        "         compare | repair | sync | find | export",
    ]
    return "\n".join(lines)


async def _find(find_text: str, repos: Any = None) -> str:
    """Search text in MEMORY.md entries."""
    md_path = _get_memory_md_path()
    md_memories = _parse_memory_md(md_path)

    results = []
    for k, v in md_memories.items():
        if find_text.lower() in v.lower() or find_text.lower() in k.lower():
            preview = v[:120].replace("\n", " ")
            results.append((k, preview))

    if not results:
        return f"🔍 No se encontraron resultados para '{find_text}'."

    lines = [f"🔍 **{len(results)} resultados** para '{find_text}':", ""]
    for k, preview in sorted(results)[:20]:
        lines.append(f"  📄 **{k}**")
        lines.append(f"     {preview}...")
        lines.append("")
    if len(results) > 20:
        lines.append(f"  ... y {len(results) - 20} mas.")
    return "\n".join(lines)


async def _export(fmt: str = "text", repos: Any = None) -> str:
    """Export MEMORY.md as JSON."""
    md_path = _get_memory_md_path()
    md_memories = _parse_memory_md(md_path)

    data = [{"key": k, "value": v} for k, v in sorted(md_memories.items())]
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)

    lines = [f"📤 **EXPORT: {len(data)} entradas**", ""]
    for entry in data[:30]:
        preview = entry["value"][:80].replace("\n", " ")
        lines.append(f"  {entry['key']}: {preview}...")
    if len(data) > 30:
        lines.append(f"  ... y {len(data) - 30} mas.")
    return "\n".join(lines)
