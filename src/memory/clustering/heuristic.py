"""Heuristic topic clustering for session exchanges.

Clusters exchanges by keyword similarity. No LLM, no sklearn.
Uses Jaccard similarity on keyword sets.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Minimum Jaccard similarity to assign to existing cluster
_MIN_CLUSTER_SIMILARITY = 0.15

# Minimum similarity to MERGE two clusters
_MERGE_SIMILARITY = 0.35

# Maximum number of clusters before forced merge (safety)
_MAX_CLUSTERS = 500


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets of keywords."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


class Cluster:
    """A topic cluster with its centroid keywords and metadata."""

    def __init__(self, cluster_id: str | None = None):
        self.id: str = cluster_id or str(uuid.uuid4())
        self.label: str = ""
        self.keywords: dict[str, float] = {}       # keyword → avg weight
        self.keyword_set: set[str] = set()          # for fast Jaccard
        self.exchange_count: int = 0
        self.session_ids: set[str] = set()
        self.first_seen: str = datetime.now().isoformat()
        self.last_updated: str = self.first_seen
        self.weight: float = 1.0

    def update(self, keywords: dict[str, float], session_id: str) -> None:
        """Update cluster centroid with new exchange keywords."""
        # Weighted moving average
        n = self.exchange_count
        for kw, score in keywords.items():
            if kw in self.keywords:
                self.keywords[kw] = (self.keywords[kw] * n + score) / (n + 1)
            else:
                self.keywords[kw] = score

        self.keyword_set = set(self.keywords.keys())
        self.exchange_count += 1
        self.session_ids.add(session_id)

        # Auto-generate label from top keywords
        sorted_kw = sorted(self.keywords.items(), key=lambda x: -x[1])
        self.label = ", ".join(w for w, _ in sorted_kw[:3])

        self.last_updated = datetime.now().isoformat()

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "keywords": sorted(self.keywords.items(), key=lambda x: -x[1])[:5],
            "exchange_count": self.exchange_count,
            "session_count": len(self.session_ids),
            "first_seen": self.first_seen,
            "last_updated": self.last_updated,
            "weight": self.weight,
        }


class HeuristicClusterer:
    """In-memory cluster manager. Persists to DB via flush()."""

    def __init__(self):
        self.clusters: dict[str, Cluster] = {}

    def assign(self, keywords: dict[str, float], session_id: str) -> Cluster:
        """Assign an exchange to a cluster (existing or new).

        Returns the assigned cluster.
        """
        kw_set = set(keywords.keys())

        best_cluster = None
        best_sim = 0.0

        for cluster in self.clusters.values():
            sim = jaccard_similarity(kw_set, cluster.keyword_set)
            if sim > best_sim and sim >= _MIN_CLUSTER_SIMILARITY:
                best_sim = sim
                best_cluster = cluster

        if best_cluster is None:
            # Create new cluster
            cluster = Cluster()
            cluster.update(keywords, session_id)
            self.clusters[cluster.id] = cluster

            # Safety: if too many clusters, force merge
            if len(self.clusters) > _MAX_CLUSTERS:
                self._merge_similar()
            return cluster

        best_cluster.update(keywords, session_id)
        return best_cluster

    def assign_from_keyword_list(self, kw_list: list[tuple[str, float]],
                                  session_id: str) -> Cluster:
        """Assign using list of (keyword, score) tuples."""
        kw_dict = {w: s for w, s in kw_list}
        return self.assign(kw_dict, session_id)

    def _merge_similar(self) -> int:
        """Merge clusters with Jaccard similarity above threshold.

        Returns number of merges performed.
        """
        merged = 0
        ids = list(self.clusters.keys())

        for i in range(len(ids)):
            if ids[i] not in self.clusters:
                continue
            for j in range(i + 1, len(ids)):
                if ids[j] not in self.clusters:
                    continue
                a = self.clusters[ids[i]]
                b = self.clusters[ids[j]]
                sim = jaccard_similarity(a.keyword_set, b.keyword_set)

                if sim >= _MERGE_SIMILARITY:
                    # Merge b into a (keep the one with more exchanges)
                    if b.exchange_count > a.exchange_count:
                        a, b = b, a
                        ids[i], ids[j] = ids[j], ids[i]

                    a.exchange_count += b.exchange_count
                    a.session_ids |= b.session_ids
                    a.last_updated = max(a.last_updated, b.last_updated)
                    # Recompute keywords average
                    total = a.exchange_count
                    for kw, score in b.keywords.items():
                        if kw in a.keywords:
                            a.keywords[kw] = (a.keywords[kw] * (total - b.exchange_count) + score * b.exchange_count) / total
                        else:
                            a.keywords[kw] = score * b.exchange_count / total
                    a.keyword_set = set(a.keywords.keys())

                    # Remove b
                    del self.clusters[b.id]
                    merged += 1

        if merged:
            logger.info("Cluster merge: %d clusters merged", merged)
        return merged

    def get_cluster(self, cluster_id: str) -> Cluster | None:
        return self.clusters.get(cluster_id)

    def get_all_clusters(self) -> list[Cluster]:
        return list(self.clusters.values())

    def get_active_clusters(self, min_exchanges: int = 2) -> list[Cluster]:
        """Return clusters with at least min_exchanges."""
        return [c for c in self.clusters.values() if c.exchange_count >= min_exchanges]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the cluster state."""
        active = self.get_active_clusters(min_exchanges=1)
        return {
            "total_clusters": len(self.clusters),
            "active_clusters": len(active),
            "total_exchanges": sum(c.exchange_count for c in active),
            "labels": [c.label for c in sorted(active, key=lambda x: -x.exchange_count)[:10]],
        }


# ── DB persistence ─────────────────────────────────────────────────

async def flush_clusters_to_db(clusterer: HeuristicClusterer,
                               db_path: str,
                               mappings: Optional[list[dict[str, Any]]] = None,
                               *,
                               origin_node_id: str = "") -> int:
    """Persist in-memory clusters + exchange mappings to SQLite.

    Tables must already exist (created by memory_schema.py migrations).
    If *mappings* is provided, also inserts exchange→cluster links.

    ``origin_node_id`` records which node produced this set of clusters.
    When empty, the helper resolves it lazily from the active coordinator
    (so legacy callers that don't pass it still stamp provenance correctly).
    The column was added in memory_schema migration 017; old DBs without
    it fall back to the legacy INSERT.

    Returns count of new clusters written (UPDATEs don't increment).
    """
    import aiosqlite

    if not origin_node_id:
        from src.memory.provenance import resolve_local_node_id
        origin_node_id = resolve_local_node_id()

    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")

    # Probe whether topic_clusters has the origin_node_id column (migration 017).
    cur = await conn.execute("PRAGMA table_info(topic_clusters)")
    cols = {r[1] for r in await cur.fetchall()}
    has_origin = "origin_node_id" in cols

    count = 0
    for c in clusterer.clusters.values():
        keywords_json = json.dumps([{"word": w, "score": round(s, 3)}
                                    for w, s in sorted(c.keywords.items(), key=lambda x: -x[1])[:10]])

        cursor = await conn.execute(
            "SELECT cluster_id FROM topic_clusters WHERE cluster_id = ?",
            (c.id,)
        )
        existing = await cursor.fetchone()

        if existing:
            if has_origin:
                await conn.execute("""
                    UPDATE topic_clusters SET
                        label = ?,
                        keywords = ?,
                        session_count = ?,
                        exchange_count = ?,
                        last_updated = datetime('now'),
                        weight = ?,
                        origin_node_id = ?
                    WHERE cluster_id = ?
                """, (
                    c.label or "",
                    keywords_json,
                    len(c.session_ids) if hasattr(c, 'session_ids') else 0,
                    c.exchange_count,
                    c.weight if hasattr(c, 'weight') else 1.0,
                    origin_node_id,
                    c.id,
                ))
            else:
                await conn.execute("""
                    UPDATE topic_clusters SET
                        label = ?,
                        keywords = ?,
                        session_count = ?,
                        exchange_count = ?,
                        last_updated = datetime('now'),
                        weight = ?
                    WHERE cluster_id = ?
                """, (
                    c.label or "",
                    keywords_json,
                    len(c.session_ids) if hasattr(c, 'session_ids') else 0,
                    c.exchange_count,
                    c.weight if hasattr(c, 'weight') else 1.0,
                    c.id,
                ))
        else:
            if has_origin:
                await conn.execute("""
                    INSERT INTO topic_clusters
                    (cluster_id, label, keywords, session_count, exchange_count, first_seen, last_updated, weight, origin_node_id)
                    VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?)
                """, (
                    c.id,
                    c.label or "",
                    keywords_json,
                    len(c.session_ids) if hasattr(c, 'session_ids') else 0,
                    c.exchange_count,
                    c.weight if hasattr(c, 'weight') else 1.0,
                    origin_node_id,
                ))
            else:
                await conn.execute("""
                    INSERT INTO topic_clusters
                    (cluster_id, label, keywords, session_count, exchange_count, first_seen, last_updated, weight)
                    VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?)
                """, (
                    c.id,
                    c.label or "",
                    keywords_json,
                    len(c.session_ids) if hasattr(c, 'session_ids') else 0,
                    c.exchange_count,
                    c.weight if hasattr(c, 'weight') else 1.0,
                ))
            count += 1

    # Persist exchange→cluster mappings incrementally
    if mappings:
        for m in mappings:
            try:
                await conn.execute("""
                    INSERT OR IGNORE INTO exchange_clusters
                    (exchange_rowid, cluster_id, similarity)
                    VALUES (?, ?, ?)
                """, (
                    m["exchange_rowid"],
                    m["cluster_id"],
                    m.get("similarity", 0.0),
                ))
            except Exception:
                pass  # Skip individual failures (e.g. FK violation on stale cluster)

    await conn.commit()
    await conn.close()
    return count
