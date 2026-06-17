"""Entity linker — in-memory graph linking and DB flush helpers.

Part of FASE 2 (Entity Graph). Extracted entities are linked into
a knowledge graph by creating/updating entity nodes and detecting
relationships between co-occurring entities.
"""

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.memory.entity.extractor import canonical_name

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class EntityNode:
    """Represents an entity in the knowledge graph."""
    id: str
    name: str
    entity_type: str
    metadata: dict = field(default_factory=dict)
    mention_count: int = 1
    first_seen: str = ""
    last_seen: str = ""


@dataclass
class EntityRelation:
    """Represents a relationship between two entities."""
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    first_seen: str = ""
    last_seen: str = ""


_RELATION_DIRECTED = frozenset({"crea", "usa"})
_RELATION_UNDIRECTED = frozenset({"co_occurrence", "menciona", "relacionado_a"})

_DIRECTED_PATTERNS = [
    (r'\b(?:creó?|desarrolló?|construyó?|implementó?|escribió?|hizo)\s+(\w+)', 'crea'),
    (r'\b(?:usa?|utiliza?|emplea?|ocupa?|corre?|ejecuta?)\s+(\w+)', 'usa'),
    (r'\b(?:menciona?|habla?|refiere?|cita?)\s+(?:de|sobre|a)\s+(\w+)', 'menciona'),
    (r'\b(?:depende?|requiere?|necesita?)\s+(?:de)\s+(\w+)', 'depende_de'),
    (r'\b(?:relacionado?|conectado?|vinculado?)\s+(?:a|con)\s+(\w+)', 'relacionado_a'),
]


def _infer_relation_type(text: str, source_name: str, target_name: str) -> str:
    lower_text = text.lower()
    for pattern, rel_type in _DIRECTED_PATTERNS:
        if re.search(pattern, lower_text):
            return rel_type
    return 'co_occurrence'


class EntityLinker:
    """Links entities extracted from exchanges into a graph.

    Pure in-memory logic. Persistence is handled by EntityRepository.
    """

    def __init__(self, db_path: str | None = None):
        self._entities: dict[str, EntityNode] = {}
        self._relations: dict[tuple[str, str, str], EntityRelation] = {}
        self._entity_mentions: dict[str, set[int]] = {}

        if db_path is not None:
            self._load_existing(db_path)

    def _load_existing(self, db_path: str) -> None:
        """Load existing entities from DB to reuse their IDs."""
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, name, entity_type, mention_count, first_seen, last_seen FROM entities"
            )
            for row in cursor.fetchall():
                key = self._entity_key(row["entity_type"], row["name"])
                if key not in self._entities:
                    self._entities[key] = EntityNode(
                        id=row["id"],
                        name=row["name"],
                        entity_type=row["entity_type"],
                        mention_count=row["mention_count"],
                        first_seen=row["first_seen"],
                        last_seen=row["last_seen"],
                    )
            conn.close()
        except Exception:
            logger.warning("Could not load existing entities from %s", db_path, exc_info=True)

    def link_exchange(
        self,
        entities: list[tuple[str, str, float]],
        session_id: str,
        timestamp: str = "",
        exchange_rowid: int | None = None,
        exchange_text: str = "",
    ) -> None:
        """Process entities from an exchange.

        For each entity:
          - If exists: update last_seen, increment mention_count
          - If new: create entity node with a generated UUID

        For each pair of entities in the same exchange:
          - If relation exists: increment weight, update last_seen
          - If new: create relation with type "co_occurrence"
        """
        if not timestamp:
            timestamp = datetime.utcnow().isoformat()

        linked: list[tuple[str, str]] = []
        for entity_type, name, _score in entities:
            name = canonical_name(name)
            key = self._entity_key(entity_type, name)
            node = self._entities.get(key)
            if node is not None:
                node.last_seen = timestamp
                node.mention_count += 1
                node_id = node.id
            else:
                node_id = str(uuid.uuid4())
                node = EntityNode(
                    id=node_id,
                    name=name,
                    entity_type=entity_type,
                    first_seen=timestamp,
                    last_seen=timestamp,
                )
                self._entities[key] = node

            if exchange_rowid is not None:
                if node_id not in self._entity_mentions:
                    self._entity_mentions[node_id] = set()
                self._entity_mentions[node_id].add(exchange_rowid)

            for other_id, other_name in linked:
                if other_id == node_id:
                    continue
                inferred_type = _infer_relation_type(exchange_text, name, other_name)
                rkey = self._relation_key(node_id, other_id, inferred_type)
                rel = self._relations.get(rkey)
                if rel is not None:
                    rel.weight += 1.0
                    rel.last_seen = timestamp
                else:
                    a, b = sorted([node_id, other_id])
                    self._relations[rkey] = EntityRelation(
                        source_id=a,
                        target_id=b,
                        relation_type=inferred_type,
                        weight=1.0,
                        first_seen=timestamp,
                        last_seen=timestamp,
                    )
            linked.append((node_id, name))

    def get_entities(self) -> list[EntityNode]:
        """Return all entities."""
        return list(self._entities.values())

    def get_relations(self) -> list[EntityRelation]:
        """Return all relations."""
        return list(self._relations.values())

    def get_entity_mentions(self, entity_id: str) -> set[int]:
        return self._entity_mentions.get(entity_id, set())

    def get_entity_by_name(self, name: str, entity_type: str) -> EntityNode | None:
        """Find an entity by name + type."""
        return self._entities.get(self._entity_key(entity_type, name))

    @staticmethod
    def _entity_key(entity_type: str, name: str) -> str:
        return f"{entity_type}:{name.lower()}"

    @staticmethod
    def _relation_key(
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> tuple[str, str, str]:
        """Normalize undirected relations so (A,B) and (B,A) map to same key."""
        if relation_type in _RELATION_UNDIRECTED:
            a, b = sorted([source_id, target_id])
            return (a, b, relation_type)
        return (source_id, target_id, relation_type)


# ---------------------------------------------------------------------------
# DB flush helpers — called by the pipeline, not by EntityLinker itself
# ---------------------------------------------------------------------------


async def flush_entities_to_db(
    linker: EntityLinker,
    db_path: str,
) -> int:
    """Persist in-memory entities to SQLite via upsert.

    Tables must already exist (created by migration).
    Returns count of entities written.
    """
    count = 0
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        for entity in linker.get_entities():
            normalized_name = entity.name.lower()
            await db.execute(
                """
                INSERT INTO entities (id, name, normalized_name, entity_type, metadata, first_seen, last_seen, mention_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_name, entity_type) DO UPDATE SET
                    last_seen     = excluded.last_seen,
                    mention_count = excluded.mention_count,
                    metadata      = excluded.metadata
                """,
                (
                    entity.id,
                    entity.name,
                    normalized_name,
                    entity.entity_type,
                    json.dumps(entity.metadata),
                    entity.first_seen,
                    entity.last_seen,
                    entity.mention_count,
                ),
            )
            count += 1
        await db.commit()
    return count


async def flush_relations_to_db(
    linker: EntityLinker,
    db_path: str,
) -> int:
    """Persist in-memory relations to SQLite via upsert.

    Tables must already exist.
    Returns count of relations written.
    """
    count = 0
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        for rel in linker.get_relations():
            try:
                await db.execute(
                    """
                    INSERT INTO entity_relations (source_id, target_id, relation_type, weight, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                        weight    = excluded.weight,
                        last_seen = excluded.last_seen
                    """,
                    (
                        rel.source_id,
                        rel.target_id,
                        rel.relation_type,
                        rel.weight,
                        rel.first_seen,
                        rel.last_seen,
                    ),
                )
                count += 1
            except sqlite3.IntegrityError:
                logger.warning("Skipping entity relation with missing entity: %s → %s (%s)",
                               rel.source_id, rel.target_id, rel.relation_type)
        await db.commit()
    return count


async def flush_entity_mentions_to_db(linker: EntityLinker, db_path: str) -> int:
    """Persist entity→exchange mappings to SQLite.
    
    Tables must already exist (created by migration 005).
    Returns count of mappings written.
    """
    from datetime import datetime
    
    now = datetime.now().isoformat(timespec="seconds")
    count = 0
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        for entity_id, rowids in linker._entity_mentions.items():
            for rowid in rowids:
                try:
                    await db.execute("""
                        INSERT OR IGNORE INTO entity_mentions 
                        (entity_id, exchange_rowid, first_seen)
                        VALUES (?, ?, ?)
                    """, (entity_id, rowid, now))
                    count += 1
                except Exception:
                    pass
        await db.commit()
    return count


async def search_entities(
    query: str,
    entity_type: str | None = None,
    limit: int = 10,
    db_path: str | None = None,
    linker: EntityLinker | None = None,
) -> list[dict[str, Any]]:
    """Search entities by name (LIKE query).

    If *db_path* is provided, searches via SQLite.
    If *db_path* is None but *linker* is given, searches in-memory (for testing).
    Otherwise returns an empty list.
    """
    if db_path is not None:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            sql = "SELECT * FROM entities WHERE name LIKE ?"
            params: list[Any] = [f"%{query}%"]
            if entity_type:
                sql += " AND entity_type = ?"
                params.append(entity_type)
            sql += " ORDER BY mention_count DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    if linker is not None:
        results: list[dict[str, Any]] = []
        for entity in linker.get_entities():
            if query.lower() not in entity.name.lower():
                continue
            if entity_type is not None and entity.entity_type != entity_type:
                continue
            results.append({
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.entity_type,
                "metadata": entity.metadata,
                "mention_count": entity.mention_count,
                "first_seen": entity.first_seen,
                "last_seen": entity.last_seen,
            })
            if len(results) >= limit:
                break
        return results

    return []


async def explore_graph(
    entity_id: str,
    depth: int = 2,
    db_path: str | None = None,
    linker: EntityLinker | None = None,
) -> dict[str, Any]:
    """Recursive traversal from an entity via CTE (DB) or BFS (in-memory).

    Returns a dict with root_id, depth, entities list, and relations list.
    """
    if db_path is not None:
        return await _explore_graph_db(entity_id, depth, db_path)
    if linker is not None:
        return _explore_graph_memory(entity_id, depth, linker)
    return {"root_id": entity_id, "depth": depth, "entities": [], "relations": []}


async def _explore_graph_db(
    entity_id: str,
    depth: int,
    db_path: str,
) -> dict[str, Any]:
    """Breadth-first graph traversal via recursive CTE."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Collect connected node ids at each level via recursive CTE
        cursor = await db.execute(
            """
            WITH RECURSIVE graph AS (
                SELECT
                    CASE WHEN source_id = ? THEN target_id ELSE source_id END AS connected_id,
                    1 AS lvl
                FROM entity_relations
                WHERE source_id = ? OR target_id = ?
                UNION ALL
                SELECT
                    CASE WHEN r.source_id = g.connected_id THEN r.target_id ELSE r.source_id END,
                    g.lvl + 1
                FROM entity_relations r
                JOIN graph g
                    ON (r.source_id = g.connected_id OR r.target_id = g.connected_id)
                WHERE g.lvl < ?
            )
            SELECT DISTINCT connected_id, lvl FROM graph ORDER BY lvl
            """,
            (entity_id, entity_id, entity_id, depth),
        )
        connected = await cursor.fetchall()

        node_ids = [row["connected_id"] for row in connected]
        # Include root entity
        all_ids = [entity_id] + node_ids

        # Fetch entity details
        entities: list[dict[str, Any]] = []
        if all_ids:
            placeholders = ",".join("?" for _ in all_ids)
            cursor = await db.execute(
                f"SELECT * FROM entities WHERE id IN ({placeholders})",
                all_ids,
            )
            entities = [dict(row) for row in await cursor.fetchall()]

        # Fetch relations within the subgraph
        relations: list[dict[str, Any]] = []
        if all_ids:
            placeholders = ",".join("?" for _ in all_ids)
            cursor = await db.execute(
                f"""SELECT * FROM entity_relations
                    WHERE source_id IN ({placeholders})
                       OR target_id IN ({placeholders})""",
                all_ids + all_ids,
            )
            relations = [dict(row) for row in await cursor.fetchall()]

    return {
        "root_id": entity_id,
        "depth": depth,
        "entities": entities,
        "relations": relations,
    }


def _explore_graph_memory(
    entity_id: str,
    depth: int,
    linker: EntityLinker,
) -> dict[str, Any]:
    """BFS graph traversal entirely in memory."""
    entities_map = {e.id: e for e in linker.get_entities()}
    relations_list = linker.get_relations()

    visited: set[str] = {entity_id}
    queue: list[tuple[str, int]] = [(entity_id, 0)]

    while queue:
        current_id, lvl = queue.pop(0)
        if lvl >= depth:
            continue
        for rel in relations_list:
            other_id = None
            if rel.source_id == current_id:
                other_id = rel.target_id
            elif rel.target_id == current_id:
                other_id = rel.source_id
            if other_id is not None and other_id not in visited:
                visited.add(other_id)
                queue.append((other_id, lvl + 1))

    entities = [
        {
            "id": e.id,
            "name": e.name,
            "entity_type": e.entity_type,
            "metadata": e.metadata,
            "mention_count": e.mention_count,
            "first_seen": e.first_seen,
            "last_seen": e.last_seen,
        }
        for e in (entities_map.get(eid) for eid in visited)
        if e is not None
    ]

    return {
        "root_id": entity_id,
        "depth": depth,
        "entities": entities,
        "relations": [],
    }
