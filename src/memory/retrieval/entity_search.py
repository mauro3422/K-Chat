"""Entity search via entity_mentions + entities tables."""

from __future__ import annotations
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def entity_search(
    query: str,
    db_path: str,
    top_k: int = 20,
    source_filter: str | None = None,
    exclude_source_key: str | None = None,
) -> list[tuple[int, float]]:
    """Search for exchanges linked to entities mentioned in the query.
    
    Extracts entities from the query using the entity extractor,
    then searches entity_mentions for exchanges linked to those entities.
    
    Args:
        query: User query string.
        db_path: Path to memory.db.
        top_k: Maximum results to return.
        source_filter: Optional 'memory' or 'session' to filter by source.
        exclude_source_key: If set, exclude entries with this source_key.
    
    Returns:
        [(rowid, entity_score), ...] sorted by score descending.
        entity_score = sum of mention_count for matching entities.
    """
    from src.memory.entity.extractor import extract_entities
    
    entities = extract_entities(query)
    
    conn = sqlite3.connect(db_path)
    try:
        conditions = []
        name_params: list[Any] = []
        for _, name, _ in entities:
            conditions.append("(LOWER(e.name) = LOWER(?) OR LOWER(e.normalized_name) = LOWER(?))")
            name_params.append(name)
            name_params.append(name)
        
        if not conditions:
            return []
        
        where_clause = " OR ".join(conditions)
        
        source_join = ""
        source_where = ""
        source_params: list[Any] = []
        if source_filter:
            source_join = "JOIN vec_meta m ON m.rowid = em.exchange_rowid"
            source_where = "AND m.source = ?"
            source_params.append(source_filter)
        if exclude_source_key:
            if not source_join:
                source_join = "JOIN vec_meta m ON m.rowid = em.exchange_rowid"
            source_where += " AND m.source_key != ?"
            source_params.append(exclude_source_key)
        
        # 1. Direct entity matches (original logic)
        rows = conn.execute(
            f"""
            SELECT em.exchange_rowid as rowid, SUM(e.mention_count) as score
            FROM entity_mentions em
            JOIN entities e ON e.id = em.entity_id
            {source_join}
            WHERE ({where_clause}) {source_where}
            GROUP BY em.exchange_rowid
            ORDER BY score DESC
            LIMIT ?
            """,
            [*name_params, *source_params, top_k]
        ).fetchall()
        
        result_map: dict[int, float] = {}
        for rowid, score in rows:
            result_map[rowid] = score
        
        # 2. Entity graph traversal: find related entities via entity_relations
        entity_ids = [
            r[0] for r in conn.execute(
                f"SELECT DISTINCT e.id FROM entities e WHERE ({where_clause})",
                name_params
            ).fetchall()
        ]
        
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            related_rows = conn.execute(
                f"""
                SELECT em.exchange_rowid as rowid, SUM(e_rel.mention_count * 0.5) as score
                FROM entity_relations er
                JOIN entities e_rel ON (e_rel.id = er.target_id OR e_rel.id = er.source_id)
                JOIN entity_mentions em ON em.entity_id = e_rel.id
                {source_join}
                WHERE (er.source_id IN ({placeholders}) OR er.target_id IN ({placeholders}))
                  AND e_rel.id NOT IN ({placeholders})
                  {source_where}
                GROUP BY em.exchange_rowid
                """,
                [*entity_ids, *entity_ids, *entity_ids, *source_params]
            ).fetchall()
            
            for rowid, score in related_rows:
                result_map[rowid] = result_map.get(rowid, 0) + score
        
        if not result_map:
            return []
        
        sorted_results = sorted(result_map.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]
    finally:
        conn.close()



