from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.memory.operations._helpers import _memory_db, _sessions_db


def _backup_connection(
    conn: sqlite3.Connection,
    *,
    label: str,
    root: str | Path | None = None,
) -> str:
    project_root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    backup_root = project_root / "backups" / "memory-quality"
    backup_root.mkdir(parents=True, exist_ok=True)
    target = backup_root / f"{label}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    with sqlite3.connect(target) as destination:
        conn.backup(destination)
    return str(target)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


async def _quality_stats(repos: Any = None) -> str:
    with _memory_db(repos) as conn:
        entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        generated = conn.execute(
            """SELECT COUNT(*) FROM entities
               WHERE id LIKE 'pmi_%' OR id LIKE 'entity:concept:%'"""
        ).fetchone()[0]
        leaf_noise = conn.execute(
            """SELECT COUNT(*) FROM entities e
               WHERE e.entity_type = 'concept'
                 AND (e.id LIKE 'pmi_%' OR e.id LIKE 'entity:concept:%')
                 AND e.mention_count <= 1
                 AND (
                    SELECT COUNT(*) FROM entity_relations er
                    WHERE er.source_id=e.id OR er.target_id=e.id
                 ) <= 1"""
        ).fetchone()[0]
        relations = conn.execute("SELECT COUNT(*) FROM entity_relations").fetchone()[0]
    with _sessions_db(repos) as conn:
        empty_sessions = conn.execute(
            """SELECT COUNT(*) FROM sessions s
               WHERE NOT EXISTS (
                   SELECT 1 FROM messages m WHERE m.session_id=s.session_id
               )"""
        ).fetchone()[0]
    return (
        "MEMORY QUALITY\n"
        f"Entities: {entities} ({generated} generated, {leaf_noise} low-signal leaves)\n"
        f"Entity relations: {relations}\n"
        f"Empty sessions: {empty_sessions}"
    )


async def _prune_entities(
    *,
    dry_run: bool = True,
    confirm: bool = False,
    repos: Any = None,
) -> str:
    with _memory_db(repos) as conn:
        conn.execute("DROP TABLE IF EXISTS temp.memory_quality_entity_candidates")
        conn.execute(
            """CREATE TEMP TABLE memory_quality_entity_candidates AS
               SELECT e.id FROM entities e
               WHERE e.entity_type = 'concept'
                 AND (e.id LIKE 'pmi_%' OR e.id LIKE 'entity:concept:%')
                 AND e.mention_count <= 1
                 AND (
                    SELECT COUNT(*) FROM entity_relations er
                    WHERE er.source_id=e.id OR er.target_id=e.id
                 ) <= 1
                 AND NOT EXISTS (
                    SELECT 1 FROM entity_mentions em WHERE em.entity_id=e.id
                 )
                 AND NOT EXISTS (
                    SELECT 1 FROM memory_curated_relations mcr
                    WHERE mcr.source_id=e.id OR mcr.target_id=e.id
                 )"""
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_quality_entity_candidates"
        ).fetchone()[0]
        if dry_run or not confirm:
            return (
                f"[DRY RUN] {count} entidades conceptuales de baja señal serían podadas. "
                "Usá confirm=true para aplicar con respaldo."
            )
        backup = _backup_connection(conn, label="curated-memory-before-entity-prune")
        try:
            conn.execute("BEGIN IMMEDIATE")
            removed_relations = conn.execute(
                """DELETE FROM entity_relations
                   WHERE source_id IN (SELECT id FROM memory_quality_entity_candidates)
                      OR target_id IN (SELECT id FROM memory_quality_entity_candidates)"""
            ).rowcount
            removed_entities = conn.execute(
                """DELETE FROM entities
                   WHERE id IN (SELECT id FROM memory_quality_entity_candidates)"""
            ).rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return (
        f"Podadas {removed_entities} entidades y {removed_relations} relaciones. "
        f"Respaldo: {backup}"
    )


async def _cleanup_empty_sessions(
    *,
    dry_run: bool = True,
    confirm: bool = False,
    repos: Any = None,
) -> str:
    with _sessions_db(repos) as conn:
        conn.execute("DROP TABLE IF EXISTS temp.empty_session_candidates")
        conn.execute(
            """CREATE TEMP TABLE empty_session_candidates AS
               SELECT s.session_id FROM sessions s
               WHERE NOT EXISTS (
                   SELECT 1 FROM messages m WHERE m.session_id=s.session_id
               )"""
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM empty_session_candidates"
        ).fetchone()[0]
        if dry_run or not confirm:
            return (
                f"[DRY RUN] {count} sesiones vacías serían eliminadas. "
                "Usá confirm=true para aplicar con respaldo."
            )
        backup = _backup_connection(conn, label="sessions-before-empty-cleanup")
        try:
            conn.execute("BEGIN IMMEDIATE")
            for table in ("tool_calls", "debug_info", "chat_journal"):
                if _table_exists(conn, table):
                    conn.execute(
                        f"""DELETE FROM {table}
                            WHERE session_id IN (
                                SELECT session_id FROM empty_session_candidates
                            )"""
                    )
            removed = conn.execute(
                """DELETE FROM sessions
                   WHERE session_id IN (
                       SELECT session_id FROM empty_session_candidates
                   )"""
            ).rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return f"Eliminadas {removed} sesiones vacías. Respaldo: {backup}"


async def _backfill_historical_tool_calls(
    *,
    dry_run: bool = True,
    confirm: bool = False,
    repos: Any = None,
) -> str:
    """Recover old tool-call metadata from assistant message payloads.

    Only sessions with no rows in ``tool_calls`` are eligible. This makes the
    operation idempotent and avoids mixing reconstructed rows with complete
    runtime telemetry.
    """

    with _sessions_db(repos) as conn:
        rows = conn.execute(
            """SELECT m.session_id, m.created_at, m.tool_calls
               FROM messages m
               WHERE m.role = 'assistant'
                 AND m.tool_calls IS NOT NULL
                 AND LENGTH(TRIM(m.tool_calls)) > 4
                 AND NOT EXISTS (
                     SELECT 1 FROM tool_calls t
                     WHERE t.session_id = m.session_id
                 )
               ORDER BY m.session_id, m.created_at, m.id"""
        ).fetchall()
        recovered: list[tuple[str, str, str, str, int]] = []
        turns: dict[str, int] = {}
        malformed = 0
        for session_id, created_at, raw_calls in rows:
            try:
                calls = json.loads(raw_calls)
            except (TypeError, json.JSONDecodeError):
                malformed += 1
                continue
            if not isinstance(calls, list):
                malformed += 1
                continue
            turn = turns.get(session_id, 0)
            for call in calls:
                function = call.get("function", {}) if isinstance(call, dict) else {}
                tool_name = str(function.get("name", "")).strip()
                if not tool_name:
                    continue
                arguments = function.get("arguments", "{}")
                input_text = (
                    arguments
                    if isinstance(arguments, str)
                    else json.dumps(arguments, ensure_ascii=False)
                )
                recovered.append(
                    (str(session_id), tool_name, input_text, str(created_at), turn)
                )
            turns[session_id] = turn + 1

        session_count = len({row[0] for row in recovered})
        if dry_run or not confirm:
            return (
                f"[DRY RUN] {len(recovered)} llamadas históricas de "
                f"{session_count} sesiones serían recuperadas "
                f"({malformed} mensajes malformados omitidos). "
                "Usá confirm=true para aplicar con respaldo."
            )
        backup = _backup_connection(conn, label="sessions-before-tool-call-backfill")
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                """INSERT INTO tool_calls (
                       session_id, tool_name, input, status, created_at, turn
                   ) VALUES (?, ?, ?, 'historical', ?, ?)""",
                recovered,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return (
        f"Recuperadas {len(recovered)} llamadas históricas de {session_count} sesiones "
        f"({malformed} mensajes malformados omitidos). Respaldo: {backup}"
    )


async def _prune_indirect_cooccurrence(
    *,
    entity_id: str,
    dry_run: bool = True,
    confirm: bool = False,
    repos: Any = None,
) -> str:
    """Remove PMI edges leaking through a root's typed semantic neighbors."""

    query = str(entity_id or "").strip()
    if not query:
        return "[ERROR] Se requiere entity_id o nombre de entidad."
    with _memory_db(repos) as conn:
        root = conn.execute(
            """SELECT id, name FROM entities
               WHERE id = ? OR lower(name) = lower(?)
               ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END,
                        mention_count DESC
               LIMIT 1""",
            (query, query, query),
        ).fetchone()
        if root is None:
            return f"[ERROR] No se encontró la entidad '{query}'."
        root_id, root_name = str(root[0]), str(root[1])
        conn.execute("DROP TABLE IF EXISTS temp.semantic_anchor_candidates")
        conn.execute(
            """CREATE TEMP TABLE semantic_anchor_candidates (id TEXT PRIMARY KEY)"""
        )
        conn.execute(
            "INSERT INTO semantic_anchor_candidates (id) VALUES (?)",
            (root_id,),
        )
        conn.execute(
            """INSERT OR IGNORE INTO semantic_anchor_candidates (id)
               SELECT CASE
                        WHEN source_id = ? THEN target_id
                        ELSE source_id
                      END
               FROM entity_relations
               WHERE (source_id = ? OR target_id = ?)
                 AND lower(relation_type) NOT IN ('co_occurrence', 'promoted_to')""",
            (root_id, root_id, root_id),
        )
        conn.execute("DROP TABLE IF EXISTS temp.indirect_cooccurrence_candidates")
        conn.execute(
            """CREATE TEMP TABLE indirect_cooccurrence_candidates AS
               SELECT er.rowid
               FROM entity_relations er
               WHERE lower(er.relation_type) = 'co_occurrence'
                 AND (
                     er.source_id IN (SELECT id FROM semantic_anchor_candidates)
                     OR er.target_id IN (SELECT id FROM semantic_anchor_candidates)
                 )"""
        )
        edge_count = conn.execute(
            "SELECT COUNT(*) FROM indirect_cooccurrence_candidates"
        ).fetchone()[0]
        anchors = [
            row[0]
            for row in conn.execute(
                """SELECT e.name FROM entities e
                   JOIN semantic_anchor_candidates a ON a.id=e.id
                   ORDER BY e.name"""
            ).fetchall()
        ]
        conn.commit()
        if dry_run or not confirm:
            return (
                f"[DRY RUN] {edge_count} conexiones co_occurrence indirectas de "
                f"'{root_name}' serían eliminadas. Anclas: {', '.join(anchors)}. "
                "Usá confirm=true para aplicar con respaldo."
            )
        backup = _backup_connection(
            conn, label="curated-memory-before-indirect-cooccurrence-prune"
        )
        try:
            conn.execute("BEGIN IMMEDIATE")
            removed_edges = conn.execute(
                """DELETE FROM entity_relations
                   WHERE rowid IN (
                       SELECT rowid FROM indirect_cooccurrence_candidates
                   )"""
            ).rowcount
            removed_entities = conn.execute(
                """DELETE FROM entities
                   WHERE entity_type = 'concept'
                     AND (id LIKE 'pmi_%' OR id LIKE 'entity:concept:%')
                     AND NOT EXISTS (
                         SELECT 1 FROM entity_relations er
                         WHERE er.source_id=entities.id OR er.target_id=entities.id
                     )
                     AND NOT EXISTS (
                         SELECT 1 FROM entity_mentions em
                         WHERE em.entity_id=entities.id
                     )
                     AND NOT EXISTS (
                         SELECT 1 FROM memory_curated_relations cr
                         WHERE cr.source_id=entities.id OR cr.target_id=entities.id
                     )"""
            ).rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return (
        f"Eliminadas {removed_edges} conexiones co_occurrence indirectas de "
        f"'{root_name}' y {removed_entities} conceptos huérfanos. Respaldo: {backup}"
    )


async def _rebuild_topic_relations(
    *,
    dry_run: bool = True,
    confirm: bool = False,
    repos: Any = None,
) -> str:
    from src.memory.clustering.relations import detect_relations

    with _memory_db(repos) as conn:
        rows = conn.execute(
            "SELECT cluster_id, keywords FROM topic_clusters WHERE weight > 0"
        ).fetchall()
        clusters = []
        for cluster_id, raw_keywords in rows:
            try:
                keywords = json.loads(raw_keywords or "[]")
            except json.JSONDecodeError:
                keywords = []
            clusters.append({"id": cluster_id, "keywords": keywords})
        relations = detect_relations(clusters)
        if dry_run or not confirm:
            return (
                f"[DRY RUN] {len(relations)} relaciones entre {len(clusters)} "
                "clusters serían reconstruidas. Usá confirm=true para aplicar."
            )
        backup = _backup_connection(conn, label="curated-memory-before-topic-rebuild")
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM topic_relations")
            now = datetime.now().isoformat(timespec="seconds")
            for relation in relations:
                conn.execute(
                    """INSERT INTO topic_relations (
                           source_id, target_id, shared_keywords, shared_count,
                           relationship_type, weight, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        relation["source_id"],
                        relation["target_id"],
                        json.dumps(relation["shared_keywords"], ensure_ascii=False),
                        relation["shared_count"],
                        relation["relationship_type"],
                        relation["weight"],
                        now,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return (
        f"Reconstruidas {len(relations)} relaciones entre {len(clusters)} clusters. "
        f"Respaldo: {backup}"
    )


__all__ = [
    "_backfill_historical_tool_calls",
    "_cleanup_empty_sessions",
    "_prune_indirect_cooccurrence",
    "_prune_entities",
    "_quality_stats",
    "_rebuild_topic_relations",
]
