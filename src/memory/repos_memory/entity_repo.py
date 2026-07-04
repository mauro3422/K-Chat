"""EntityRepository — entity graph storage in memory.db.

Stores entities (people, topics, concepts) and their relations for
graph-based memory retrieval and exploration.

Creates a fresh aiosqlite connection per operation to avoid thread lifecycle
issues with aiosqlite's background worker threads.
"""

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from src.memory.repos_memory.sqlite_helper import create_memory_db_connection

logger = logging.getLogger(__name__)


class EntityRepository:
    """Repository for entity graph operations on memory.db.

    Stores entities and their typed relations. Supports recursive graph
    traversal via CTE for exploring entity neighborhoods.
    """

    _table_name = "entities"

    def __init__(self, conn: Any = None) -> None:
        self._conn = conn

    async def _get_conn(self) -> Any:
        """Return the injected connection or create a fresh one."""
        if self._conn is not None:
            return self._conn
        return await self._create_conn()

    async def _create_conn(self) -> Any:
        """Create a fresh aiosqlite connection to memory.db."""
        return await create_memory_db_connection()

    @asynccontextmanager
    async def _connection(self):
        conn = await self._get_conn()
        try:
            yield conn
        finally:
            if self._conn is None:
                await conn.close()

    async def _ensure_table(self, conn: Any) -> None:
        """Ensure the entities table exists (lazy init)."""
        try:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
            )
            row = await cur.fetchone()
            if not row:
                from src.memory.memory_schema import init_memory_db
                await init_memory_db()
        except Exception:
            from src.memory.memory_schema import init_memory_db
            await init_memory_db()

    async def upsert_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        metadata: dict = None,
        timestamp: str = "",
        origin_node_id: str = "",
    ) -> None:
        """INSERT OR UPDATE an entity.

        ``origin_node_id`` records which node extracted this entity. It is
        advisory — it doesn't affect the ON CONFLICT(id) upsert behavior,
        so two nodes extracting the same entity_id converge to a single row
        with the last writer's origin_node_id. Useful for the curator when
        reconciling clusters across nodes.
        """
        async with self._connection() as conn:
            try:
                import json
                meta_json = json.dumps(metadata) if metadata else "{}"
                try:
                    await conn.execute(
                        """INSERT INTO entities (id, name, entity_type, metadata, first_seen, last_seen, mention_count, origin_node_id)
                           VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                           ON CONFLICT(id) DO UPDATE SET
                               name = excluded.name,
                               metadata = excluded.metadata,
                               last_seen = excluded.last_seen,
                               mention_count = mention_count + 1,
                               origin_node_id = excluded.origin_node_id""",
                        (entity_id, name, entity_type, meta_json, timestamp, timestamp, origin_node_id),
                    )
                except Exception:
                    # Pre-migration-016 DB: origin_node_id column missing.
                    await conn.execute(
                        """INSERT INTO entities (id, name, entity_type, metadata, first_seen, last_seen, mention_count)
                           VALUES (?, ?, ?, ?, ?, ?, 1)
                           ON CONFLICT(id) DO UPDATE SET
                               name = excluded.name,
                               metadata = excluded.metadata,
                               last_seen = excluded.last_seen,
                               mention_count = mention_count + 1""",
                        (entity_id, name, entity_type, meta_json, timestamp, timestamp),
                    )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def upsert_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str = "co_occurrence",
        weight: float = 1.0,
        timestamp: str = "",
    ) -> None:
        """INSERT OR UPDATE a relation."""
        async with self._connection() as conn:
            try:
                await conn.execute(
                    """INSERT INTO entity_relations (source_id, target_id, relation_type, weight, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                           weight = excluded.weight,
                           last_seen = excluded.last_seen""",
                    (source_id, target_id, relation_type, weight, timestamp, timestamp),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def upsert_curated_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float = 1.0,
        candidate_id: str = "",
        provenance: dict[str, Any] | None = None,
        evidence: str = "",
        metadata: dict[str, Any] | None = None,
        timestamp: str = "",
    ) -> str:
        """INSERT OR UPDATE a curator-approved relation with provenance."""

        relation_id = hashlib.sha256(
            "|".join([source_id, target_id, relation_type, candidate_id]).encode("utf-8")
        ).hexdigest()[:24]
        provenance_json = json.dumps(provenance or {}, ensure_ascii=False, sort_keys=True)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        async with self._connection() as conn:
            try:
                await conn.execute(
                    """INSERT INTO memory_curated_relations (
                           relation_id, source_id, target_id, relation_type, weight,
                           candidate_id, provenance, evidence, metadata,
                           first_seen, last_seen, promoted_at
                       )
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(relation_id) DO UPDATE SET
                           weight = excluded.weight,
                           provenance = excluded.provenance,
                           evidence = excluded.evidence,
                           metadata = excluded.metadata,
                           last_seen = excluded.last_seen,
                           promoted_at = excluded.promoted_at""",
                    (
                        relation_id,
                        source_id,
                        target_id,
                        relation_type,
                        weight,
                        candidate_id,
                        provenance_json,
                        evidence,
                        metadata_json,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                await conn.commit()
                return relation_id
            except Exception:
                await conn.rollback()
                raise

    async def get_curated_relation(
        self,
        relation_id: str = "",
        *,
        source_id: str = "",
        target_id: str = "",
        relation_type: str = "",
        candidate_id: str = "",
    ) -> dict[str, Any] | None:
        """Fetch a curator-approved relation by id or identity."""

        async with self._connection() as conn:
            if relation_id:
                cursor = await conn.execute(
                    "SELECT * FROM memory_curated_relations WHERE relation_id = ?",
                    (relation_id,),
                )
            else:
                cursor = await conn.execute(
                    """SELECT * FROM memory_curated_relations
                       WHERE source_id = ? AND target_id = ? AND relation_type = ? AND candidate_id = ?""",
                    (source_id, target_id, relation_type, candidate_id),
                )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _decode_curated_relation(dict(row))

    async def list_curated_relations_for_node(
        self,
        node_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List curator-approved relations touching a graph node."""

        async with self._connection() as conn:
            cursor = await conn.execute(
                """SELECT * FROM memory_curated_relations
                   WHERE source_id = ? OR target_id = ?
                   ORDER BY promoted_at DESC, last_seen DESC
                   LIMIT ?""",
                (node_id, node_id, limit),
            )
            rows = await cursor.fetchall()
        return [_decode_curated_relation(dict(row)) for row in rows]

    async def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search entities by name using LIKE."""
        pattern = f"%{query}%"
        async with self._connection() as conn:
            if entity_type:
                cursor = await conn.execute(
                    "SELECT * FROM entities WHERE name LIKE ? AND entity_type = ? ORDER BY mention_count DESC LIMIT ?",
                    (pattern, entity_type, limit),
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM entities WHERE name LIKE ? ORDER BY mention_count DESC LIMIT ?",
                    (pattern, limit),
                )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Get a single entity by ID."""
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM entities WHERE id = ?",
                (entity_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_entities(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get all entities ordered by mention_count DESC."""
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM entities ORDER BY mention_count DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def explore_graph(
        self,
        entity_id: str,
        depth: int = 2,
    ) -> list[dict[str, Any]]:
        """CTE recursive traversal from an entity (bidirectional).

        Returns list of dicts with entity and relation info at each depth.
        """
        async with self._connection() as conn:
            cursor = await conn.execute(
                """WITH RECURSIVE chain AS (
                    SELECT source_id, target_id, relation_type, 1 AS depth
                    FROM entity_relations WHERE source_id = ? OR target_id = ?
                    UNION ALL
                    SELECT r.source_id, r.target_id, r.relation_type, c.depth + 1
                    FROM entity_relations r
                    JOIN chain c ON (r.source_id = c.target_id OR r.target_id = c.source_id)
                    WHERE c.depth < ?
                )
                SELECT DISTINCT e.id, e.name, e.entity_type, c.relation_type, c.depth
                FROM chain c
                JOIN entities e ON e.id IN (c.source_id, c.target_id)
                WHERE e.id != ?
                ORDER BY c.depth""",
                (entity_id, entity_id, depth, entity_id),
            )
            rows = await cursor.fetchall()
        result = [dict(row) for row in rows]
        if not result:
            return await self._explore_raw_relations(entity_id, depth=depth)
        return result

    async def _explore_raw_relations(
        self,
        node_id: str,
        depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Fallback traversal for graph nodes that are not rows in entities."""

        async with self._connection() as conn:
            cursor = await conn.execute(
                """WITH RECURSIVE chain AS (
                    SELECT source_id, target_id, relation_type, weight, 1 AS depth
                    FROM entity_relations WHERE source_id = ? OR target_id = ?
                    UNION ALL
                    SELECT r.source_id, r.target_id, r.relation_type, r.weight, c.depth + 1
                    FROM entity_relations r
                    JOIN chain c ON (r.source_id = c.target_id OR r.target_id = c.source_id)
                    WHERE c.depth < ?
                )
                SELECT DISTINCT source_id, target_id, relation_type, weight, depth
                FROM chain
                ORDER BY depth, weight DESC""",
                (node_id, node_id, depth),
            )
            rows = await cursor.fetchall()

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int]] = set()
        for row in rows:
            source = row["source_id"]
            target = row["target_id"]
            neighbor = target if source == node_id else source
            if neighbor == node_id:
                continue
            key = (neighbor, row["relation_type"], row["depth"])
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "id": neighbor,
                    "name": _node_label(neighbor),
                    "entity_type": _node_type(neighbor),
                    "relation_type": row["relation_type"],
                    "weight": row["weight"],
                    "depth": row["depth"],
                    "source_id": source,
                    "target_id": target,
                }
            )
        return results

    async def get_entity_by_name(self, name: str, entity_type: str) -> dict[str, Any] | None:
        """Get an entity by name and type."""
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM entities WHERE name = ? AND entity_type = ?",
                (name, entity_type),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def count(self) -> int:
        """Return the total number of entities."""
        async with self._connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) as cnt FROM entities")
            row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def delete(self, entity_id: str) -> bool:
        """Delete an entity by ID. Returns True if deleted."""
        async with self._connection() as conn:
            try:
                cursor = await conn.execute(
                    "DELETE FROM entities WHERE id = ?",
                    (entity_id,),
                )
                await conn.commit()
                return cursor.rowcount > 0
            except Exception:
                await conn.rollback()
                raise


__all__ = ["EntityRepository"]


def _node_type(node_id: str) -> str:
    prefix = node_id.split(":", 1)[0] if ":" in node_id else "node"
    return {
        "memory": "memory",
        "candidate": "candidate",
        "inbox": "inbox",
        "inbox_group": "inbox_group",
        "session": "session",
        "entity": "entity",
    }.get(prefix, prefix or "node")


def _node_label(node_id: str) -> str:
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def _decode_curated_relation(row: dict[str, Any]) -> dict[str, Any]:
    for field in ("provenance", "metadata"):
        value = row.get(field)
        if isinstance(value, str):
            try:
                row[field] = json.loads(value or "{}")
            except json.JSONDecodeError:
                row[field] = {"raw": value}
    return row
