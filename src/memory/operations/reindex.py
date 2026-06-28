from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Any

from src.memory.content_hash import memory_hashes
from src.memory.operations._helpers import (
    _get_memory_db,
    _memory_db,
    _sessions_db,
)

logger = logging.getLogger(__name__)


def _find_existing_memory_vector(store: Any, key: str, raw_hash: str, content_hash: str) -> int | None:
    try:
        conn = store._get_conn()
        row = conn.execute(
            """
            SELECT rowid
            FROM vec_meta
            WHERE source = 'memory'
              AND source_key = ?
              AND (
                content_hash = ?
                OR hash = ?
                OR hash = ?
              )
            LIMIT 1
            """,
            (key, content_hash, content_hash, raw_hash),
        ).fetchone()
        if row is None:
            return None
        rowid = int(row[0])
        conn.execute(
            "UPDATE vec_meta SET hash = ?, content_hash = ? WHERE rowid = ?",
            (raw_hash, content_hash, rowid),
        )
        conn.commit()
        return rowid
    except Exception:
        logger.debug("Failed to check existing memory vector for %s", key, exc_info=True)
        return None


async def _reindex_memories(dry_run: bool = False, repos: Any = None) -> str:
    mem = repos.memory if repos else None
    if mem is None:
        return "[ERROR] Memory system not available."

    all_mem = await mem.memory_index.get_all()
    if dry_run:
        return f"[DRY RUN] Se reindexarian {len(all_mem)} entradas de MEMORY.md."

    store = mem.vector_store
    count = 0
    skipped = 0
    errors = 0
    from src.memory.embeddings.service import generate_embedding

    for entry in all_mem:
        key = entry["key"]
        value = entry["value"]
        raw_hash, content_hash = memory_hashes(value)
        try:
            if _find_existing_memory_vector(store, key, raw_hash, content_hash) is not None:
                skipped += 1
                continue
            store.delete_by_source(key, source="memory")
            vec = await asyncio.to_thread(generate_embedding, value)
            store.insert(
                vec,
                source="memory",
                source_key=key,
                text=value[:500],
                hash=raw_hash,
                content_hash=content_hash,
            )
            count += 1
        except Exception as e:
            logger.warning("Error reindexando %s: %s", key, e)
            errors += 1

    total = store.count()
    return f"Reindexadas {count} entradas ({skipped} sin cambios, {errors} errores). Total vectores: {total}."


async def _reindex_sessions(dry_run: bool = False, repos: Any = None) -> str:
    from src.memory.vectorize_sessions import vectorize_all_sessions

    if repos is None:
        return "[ERROR] Memory system not available."

    if dry_run:
        with _sessions_db(repos) as sdb:
            sdb.row_factory = sqlite3.Row
            sessions = sdb.execute("""
                SELECT session_id, name, real_msgs FROM (
                    SELECT s.session_id, s.name,
                        (SELECT COUNT(*) FROM messages m
                         WHERE m.session_id = s.session_id
                         AND m.role='user' AND LENGTH(m.content) > 20
                        ) as real_msgs
                    FROM sessions s
                ) WHERE real_msgs > 0 ORDER BY real_msgs DESC
            """).fetchall()
        lines = [f"[DRY RUN] Sesiones a vectorizar ({len(sessions)}):"]
        for s in sessions:
            lines.append(f"  - {s['session_id'][:12]}... [{s['real_msgs']} msgs] {s['name'] or '(sin nombre)'}")
        return "\n".join(lines)

    results = await vectorize_all_sessions(dry_run=False, repos=repos)
    total = sum(results.values())

    store = repos.memory.vector_store
    vec_total = store.count()

    with _memory_db(repos) as conn:
        cc = rc = 0
        try:
            cc = conn.execute("SELECT COUNT(*) FROM topic_clusters").fetchone()[0]
            rc = conn.execute("SELECT COUNT(*) FROM topic_relations").fetchone()[0]
        except Exception:
            logger.warning("Failed to count clusters/relations", exc_info=True)

    return f"Vectorizadas {len(results)} sesiones, {total} exchanges. Clusters: {cc} | Relaciones: {rc} | Vectores: {vec_total}."


async def _reindex_single_session(session_id: str, dry_run: bool = False, repos: Any = None) -> str:
    with _sessions_db(repos) as sdb:
        sdb.row_factory = sqlite3.Row
        row = sdb.execute("SELECT name FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return f"[ERROR] No existe la sesion {session_id[:16]}..."
    if dry_run:
        return f"[DRY RUN] Se vectorizaria: {row['name'] or '(sin nombre)'}"

    from src.memory.vectorize_sessions import vectorize_session
    from src.memory.clustering.heuristic import HeuristicClusterer, flush_clusters_to_db

    clusterer = HeuristicClusterer()
    count, noise_count, mappings, _entities = await vectorize_session(session_id, clusterer=clusterer, repos=repos)

    if mappings:
        await flush_clusters_to_db(clusterer, _get_memory_db(), mappings=mappings)

    store = repos.memory.vector_store if repos else None
    total = store.count() if store else 0
    return f"Sesion '{row['name'] or session_id[:16]}': {count} exchanges ({noise_count} noise, {len(mappings)} clusters). Total store: {total}."
