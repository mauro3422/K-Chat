"""Relation detection between topic clusters.

Uses shared keywords to determine relationships.
No LLM, no sklearn — pure set arithmetic.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum shared keywords to consider a relation
_MIN_SHARED_KEYWORDS = 2

# Strong relation threshold
_STRONG_RELATION_THRESHOLD = 3


def detect_relations(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect relations between clusters based on shared keywords.

    Args:
        clusters: List of cluster dicts with at least 'id', 'keywords'.

    Returns:
        List of relation dicts with:
            source_id, target_id, shared_keywords[], relationship_type, weight
    """
    # Build keyword → cluster_id map
    kw_to_clusters: dict[str, set[str]] = {}
    cluster_keywords: dict[str, set[str]] = {}

    for c in clusters:
        cid = c["id"]
        # keywords is either list of [word, score] or list of {"word": ..., "score": ...}
        raw_kw = c.get("keywords", [])
        if raw_kw and isinstance(raw_kw[0], (list, tuple)):
            kw_set = {w for w, _ in raw_kw}
        else:
            kw_set = {k["word"] for k in raw_kw} if raw_kw else set()

        cluster_keywords[cid] = kw_set
        for kw in kw_set:
            if kw not in kw_to_clusters:
                kw_to_clusters[kw] = set()
            kw_to_clusters[kw].add(cid)

    # Find relations
    relations: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for kw, cids in kw_to_clusters.items():
        cid_list = list(cids)
        for i in range(len(cid_list)):
            for j in range(i + 1, len(cid_list)):
                a, b = cid_list[i], cid_list[j]
                pair = (a, b) if a < b else (b, a)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                a, b = pair

                shared = cluster_keywords[a] & cluster_keywords[b]
                n_shared = len(shared)

                if n_shared >= _MIN_SHARED_KEYWORDS:
                    weight = n_shared / max(len(cluster_keywords[a] | cluster_keywords[b]), 1)

                    if n_shared >= _STRONG_RELATION_THRESHOLD:
                        rel_type = "strongly_related"
                    else:
                        rel_type = "related"

                    relations.append({
                        "source_id": a,
                        "target_id": b,
                        "shared_keywords": list(shared),
                        "shared_count": n_shared,
                        "relationship_type": rel_type,
                        "weight": round(weight, 3),
                    })

    return relations


async def flush_relations_to_db(relations: list[dict[str, Any]],
                                db_path: str) -> int:
    """Persist relations to SQLite.

    Tables must already exist (created by memory_schema.py migrations).
    """
    import aiosqlite

    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")

    from datetime import datetime
    now = datetime.now().isoformat()

    count = 0
    for rel in relations:
        await conn.execute("""
            INSERT OR IGNORE INTO topic_relations
            (source_id, target_id, shared_keywords, shared_count, relationship_type, weight, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            rel["source_id"], rel["target_id"],
            json.dumps(rel["shared_keywords"]),
            rel["shared_count"], rel["relationship_type"],
            rel["weight"], now,
        ))
        count += 1

    await conn.commit()
    await conn.close()
    return count
