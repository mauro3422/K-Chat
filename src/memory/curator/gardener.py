"""Memory Gardener — prunes, merges, and cleans up memory.

Responsibilities:
- Archive low-relevance entries (relevance_score < threshold + no queries + old)
- Merge duplicate vec_meta entries (same hash, different rowids)
- Clean up clusters with only 1 exchange
- Remove low-weight entity relations (casual co-occurrences)
- Report actions taken

Dry run: python3 -m src.memory.curator.gardener --dry
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _get_memory_db_path() -> str:
    from src.memory.memory_db_path import resolve_memory_db_path
    return resolve_memory_db_path()


def _get_sessions_db_path() -> str:
    """Get sessions.db path using the project's path resolver."""
    import os
    try:
        from src.memory.db_path import resolve_db_path
        return resolve_db_path()
    except ImportError:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(root, "memory", "kairos_memory.db")


# ── Configuration ──────────────────────────────────────────────────

# Thresholds (tunable via kwargs)
_DEFAULT_CONFIG: dict[str, Any] = {
    "low_relevance_threshold": 0.3,       # Entries below this score are candidates for pruning
    "min_query_count": 1,                  # Entries with 0 queries AND low score are pruned
    "max_age_days": 30,                    # Entries older than this AND low score are pruned
    "min_cluster_exchanges": 2,            # Clusters with fewer exchanges are merged
    "min_entity_weight": 2.0,              # Entity relations below this weight are removed
    "vector_ttl_days": 90,                 # Delete vec_meta entries older than this (hard TTL)
    "dry_run": False,
}


# ── Gardener actions ───────────────────────────────────────────────

def prune_low_relevance(config: dict[str, Any]) -> dict[str, Any]:
    """Find vec_meta entries with low relevance_score, no queries, and old.
    
    Thresholds from config:
      - relevance_score < low_relevance_threshold
      - query_count < min_query_count
      - created_at older than max_age_days
    
    Instead of deleting, we set relevance_score = 0.0 (soft archive)
    so they can still be found if explicitly searched.
    
    Returns summary dict.
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)
    
    threshold = config["low_relevance_threshold"]
    min_queries = config["min_query_count"]
    max_age = config["max_age_days"]
    cutoff = (datetime.now() - timedelta(days=max_age)).isoformat()
    
    candidates = conn.execute("""
        SELECT rowid, source, source_key, relevance_score, query_count, created_at
        FROM vec_meta
        WHERE relevance_score < ?
          AND query_count < ?
          AND created_at < ?
        ORDER BY relevance_score ASC
    """, (threshold, min_queries, cutoff)).fetchall()
    
    count = len(candidates)
    if not config["dry_run"] and count > 0:
        conn.execute("""
            UPDATE vec_meta 
            SET relevance_score = 0.0 
            WHERE rowid IN ({})
        """.format(",".join("?" for _ in [r[0] for r in candidates])), 
        [r[0] for r in candidates])
        conn.commit()
    
    conn.close()
    
    return {
        "action": "prune_low_relevance",
        "candidates_found": count,
        "pruned": 0 if config["dry_run"] else count,
        "threshold": threshold,
        "min_queries": min_queries,
        "max_age_days": max_age,
    }


def prune_old_vectors(config: dict[str, Any]) -> dict[str, Any]:
    """Delete vec_meta entries older than vector_ttl_days (hard TTL).

    Unlike prune_low_relevance which soft-archives, this actually deletes
    old vectors and their entries to reclaim space.

    Returns summary dict.
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)

    max_age = config["vector_ttl_days"]
    cutoff = (datetime.now() - timedelta(days=max_age)).isoformat()

    candidates = conn.execute("""
        SELECT rowid, source, source_key, created_at
        FROM vec_meta
        WHERE created_at < ?
          AND created_at != ''
        ORDER BY created_at ASC
    """, (cutoff,)).fetchall()

    count = len(candidates)
    if not config["dry_run"] and count > 0:
        for (rowid, source, source_key, created_at) in candidates:
            conn.execute("DELETE FROM vec_entries WHERE rowid = ?", (rowid,))
        conn.execute("""
            DELETE FROM vec_meta
            WHERE created_at < ?
              AND created_at != ''
        """, (cutoff,))
        conn.commit()
        deleted = conn.total_changes
    else:
        deleted = 0

    conn.close()

    return {
        "action": "prune_old_vectors",
        "candidates_found": count,
        "deleted": 0 if config["dry_run"] else deleted,
        "ttl_days": max_age,
    }


def merge_duplicate_hashes(config: dict[str, Any]) -> dict[str, Any]:
    """Find vec_meta entries with the same hash and merge them.
    
    Keeps the entry with highest relevance_score, sums query_count,
    updates last_accessed to the most recent.
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)
    
    # Find duplicate hashes
    dupes = conn.execute("""
        SELECT hash, COUNT(*) as cnt, 
               MAX(relevance_score) as best_score,
               SUM(query_count) as total_queries,
               MAX(last_accessed) as latest_access
        FROM vec_meta
        WHERE hash != '' AND hash IS NOT NULL
        GROUP BY hash
        HAVING COUNT(*) > 1
    """).fetchall()
    
    merged = 0
    if not config["dry_run"]:
        for dupe in dupes:
            h = dupe[0]
            # Keep the one with highest score
            keeper = conn.execute("""
                SELECT rowid FROM vec_meta 
                WHERE hash = ? 
                ORDER BY relevance_score DESC, query_count DESC 
                LIMIT 1
            """, (h,)).fetchone()
            
            if keeper:
                # Delete from vec_entries first (in case no CASCADE trigger exists)
                conn.execute(
                    "DELETE FROM vec_entries WHERE rowid IN (SELECT rowid FROM vec_meta WHERE hash = ? AND rowid != ?)",
                    (h, keeper[0])
                )
                # Then delete from vec_meta
                conn.execute(
                    "DELETE FROM vec_meta WHERE hash = ? AND rowid != ?",
                    (h, keeper[0])
                )
                
                # Update keeper with merged stats
                conn.execute("""
                    UPDATE vec_meta SET 
                        query_count = ?,
                        last_accessed = ?
                    WHERE rowid = ?
                """, (dupe[3], dupe[4], keeper[0]))
                merged += 1
        
        conn.commit()
    
    conn.close()
    
    return {
        "action": "merge_duplicate_hashes",
        "duplicate_groups": len(dupes),
        "merged": merged,
    }


def cleanup_orphan_clusters(config: dict[str, Any]) -> dict[str, Any]:
    """Find clusters with fewer exchanges than threshold and merge them.
    
    Low-exchange clusters that haven't grown in 30 days get archived
    (weight set to 0).
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)
    
    min_ex = config["min_cluster_exchanges"]
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    
    orphans = conn.execute("""
        SELECT tc.cluster_id, tc.label, tc.exchange_count, tc.weight
        FROM topic_clusters tc
        WHERE tc.exchange_count < ?
          AND tc.last_updated < ?
        ORDER BY tc.exchange_count ASC
    """, (min_ex, cutoff)).fetchall()
    
    count = len(orphans)
    if not config["dry_run"] and count > 0:
        for o in orphans:
            conn.execute("UPDATE topic_clusters SET weight = 0.0 WHERE cluster_id = ?", (o[0],))
        conn.commit()
    
    conn.close()
    
    return {
        "action": "cleanup_orphan_clusters",
        "orphans_found": count,
        "archived": 0 if config["dry_run"] else count,
        "min_exchanges": min_ex,
    }


def prune_entity_relations(config: dict[str, Any]) -> dict[str, Any]:
    """Remove entity relations with weight below threshold.
    
    These are casual co-occurrences that don't represent meaningful connections.
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)
    
    min_w = config["min_entity_weight"]
    
    weak = conn.execute("""
        SELECT COUNT(*) FROM entity_relations WHERE weight < ?
    """, (min_w,)).fetchone()[0]
    
    removed = 0
    if not config["dry_run"] and weak > 0:
        conn.execute("DELETE FROM entity_relations WHERE weight < ?", (min_w,))
        conn.commit()
        removed = conn.total_changes
    
    conn.close()
    
    return {
        "action": "prune_entity_relations",
        "weak_relations_found": weak,
        "removed": removed,
        "min_weight": min_w,
    }


def cleanup_retrieval_log(config: dict[str, Any]) -> dict[str, Any]:
    """Delete retrieval_log entries older than 30 days.

    The retrieval_log table grows unbounded with every hybrid search.
    This action prunes entries older than 30 days to keep the table
    at a manageable size.
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)

    old = conn.execute(
        "SELECT COUNT(*) FROM retrieval_log WHERE retrieved_at < date('now', '-30 days')"
    ).fetchone()[0]

    deleted = 0
    if not config["dry_run"] and old > 0:
        conn.execute(
            "DELETE FROM retrieval_log WHERE retrieved_at < date('now', '-30 days')"
        )
        conn.commit()
        deleted = conn.total_changes

    conn.close()

    return {
        "action": "cleanup_retrieval_log",
        "old_entries_found": old,
        "deleted": deleted,
    }


def checkpoint_wal(config: dict[str, Any]) -> dict[str, Any]:
    """Run WAL checkpoint on memory.db and sessions.db to trim WAL files."""
    import sqlite3

    results = {}
    for name, path_fn in [("memory", _get_memory_db_path), ("sessions", _get_sessions_db_path)]:
        try:
            db_path = path_fn()
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                row = cursor.fetchone()
                results[name] = {
                    "busy": row[0] if row else -1,
                    "log_pages": row[1] if row else 0,
                    "checkpointed": row[2] if row else 0,
                }
            finally:
                conn.close()
        except Exception as e:
            results[name] = {"error": str(e)}

    return {
        "action": "checkpoint_wal",
        "databases": results,
    }


def merge_similar_clusters(config: dict[str, Any]) -> dict[str, Any]:
    """Periodically merge similar topic clusters to keep topics clean."""
    from src.memory.clustering.heuristic import jaccard_similarity

    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)

    try:
        rows = conn.execute(
            "SELECT cluster_id, keywords, exchange_count FROM topic_clusters WHERE weight > 0"
        ).fetchall()

        clusters = []
        for row in rows:
            try:
                kws = json.loads(row[1])
                kw_set = {k["word"] for k in kws} if isinstance(kws, list) else set()
                clusters.append({
                    "id": row[0],
                    "keywords": kw_set,
                    "exchange_count": row[2],
                })
            except Exception:
                continue

        if len(clusters) < 2:
            conn.close()
            return {"action": "merge_similar_clusters", "merged": 0, "reason": "<2 clusters"}

        threshold = 0.35
        merged = 0
        processed = set()

        for i, a in enumerate(clusters):
            if a["id"] in processed:
                continue
            for j, b in enumerate(clusters):
                if i >= j or b["id"] in processed:
                    continue
                sim = jaccard_similarity(a["keywords"], b["keywords"])
                if sim >= threshold:
                    keeper = a if a["exchange_count"] >= b["exchange_count"] else b
                    absorbed = b if keeper is a else a

                    if not config.get("dry_run", False):
                        conn.execute(
                            "UPDATE OR IGNORE exchange_clusters SET cluster_id = ? WHERE cluster_id = ?",
                            (keeper["id"], absorbed["id"])
                        )
                        conn.execute("DELETE FROM exchange_clusters WHERE cluster_id = ?", (absorbed["id"],))
                        conn.execute("DELETE FROM topic_clusters WHERE cluster_id = ?", (absorbed["id"],))
                        conn.commit()

                    processed.add(absorbed["id"])
                    merged += 1

            processed.add(a["id"])

        return {"action": "merge_similar_clusters", "merged": merged, "threshold": threshold}

    except Exception as e:
        return {"action": "merge_similar_clusters", "error": str(e)}
    finally:
        conn.close()


# ── Main entry point ───────────────────────────────────────────────

def garden(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run all gardener actions and return report.
    
    Args:
        config: Override default config. Use {"dry_run": True} for dry mode.
    
    Returns:
        List of action reports (dicts).
    """
    cfg = {**_DEFAULT_CONFIG, **(config or {})}
    dry = cfg["dry_run"]
    
    logger.info("Gardener %s (config: %s)", "DRY RUN" if dry else "RUNNING", cfg)
    
    results = [
        prune_low_relevance(cfg),
        prune_old_vectors(cfg),
        merge_duplicate_hashes(cfg),
        cleanup_orphan_clusters(cfg),
        merge_similar_clusters(cfg),
        prune_entity_relations(cfg),
        cleanup_retrieval_log(cfg),
        checkpoint_wal(cfg),
    ]
    
    for r in results:
        logger.info("  %s: %s", r["action"], r)

    # Unload embedding model if idle
    try:
        from src.memory.embeddings.service import unload_if_idle
        if unload_if_idle():
            logger.info("Embedding model unloaded after idle timeout")
    except Exception:
        pass  # Non-fatal
    
    return results


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    dry = "--dry" in sys.argv
    results = garden({"dry_run": dry})
    total = sum(r.get("candidates_found", 0) + r.get("duplicate_groups", 0) + 
                r.get("orphans_found", 0) + r.get("weak_relations_found", 0) 
                for r in results)
    print(f"\n{'DRY RUN: ' if dry else ''}{total} items processed.")
    for r in results:
        print(f"  {r['action']}: {r}")
