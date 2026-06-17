"""Cross-Session Tracer — detects patterns between sessions.

Uses retrieval_log, entity mentions, and tool_calls to find:
- Repeated queries (same topic retrieved multiple times)
- Entity co-occurrence patterns (same entities appearing together)
- Debug cycles (high tool_call error rates)

Dry run: python3 -m src.memory.curator.tracer --dry
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


def _get_memory_db_path() -> str:
    from src.memory.memory_db_path import resolve_memory_db_path
    return resolve_memory_db_path()


def _get_sessions_db_path() -> str:
    import os
    try:
        from src.memory.db_path import resolve_db_path
        return resolve_db_path()
    except ImportError:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(root, "memory", "kairos_memory.db")


# ── Configuration ──────────────────────────────────────────────────

_DEFAULT_CONFIG: dict[str, Any] = {
    "min_query_repeats": 3,          # A query repeated this many times is a pattern
    "min_entity_cooccurrence": 3,    # Entities co-occurring this many times is significant
    "lookback_days": 7,              # How many days back to analyze
    "max_patterns": 5,               # Max patterns to report
    "dry_run": False,
}


# ── Pattern detectors ──────────────────────────────────────────────

def detect_repeated_queries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Find queries that appear frequently in retrieval_log.
    
    These indicate topics the user returns to repeatedly.
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)
    
    cutoff = (datetime.now() - timedelta(days=config["lookback_days"])).isoformat()
    
    # Check if retrieval_log exists and has data
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "retrieval_log" not in tables:
        conn.close()
        return []
    
    count_check = conn.execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0]
    if count_check == 0:
        conn.close()
        return []
    
    repeated = conn.execute("""
        SELECT query, COUNT(*) as times, 
               COUNT(DISTINCT session_id) as sessions,
               ROUND(AVG(fusion_score), 3) as avg_score,
               GROUP_CONCAT(DISTINCT source) as sources
        FROM retrieval_log
        WHERE retrieved_at >= ?
          AND query != ''
        GROUP BY query
        HAVING COUNT(*) >= ?
        ORDER BY times DESC
        LIMIT ?
    """, (cutoff, config["min_query_repeats"], config["max_patterns"])).fetchall()
    
    conn.close()
    
    patterns = []
    for q, times, sessions, avg_score, sources in repeated:
        patterns.append({
            "type": "repeated_query",
            "query": q[:100],
            "times": times,
            "sessions": sessions,
            "avg_score": avg_score,
            "sources": sources or "",
        })
    
    return patterns


def detect_entity_clusters(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Find groups of entities that frequently co-occur together.
    
    Uses entity_relations with weight above threshold.
    """
    db_path = _get_memory_db_path()
    conn = sqlite3.connect(db_path)
    
    cutoff = (datetime.now() - timedelta(days=config["lookback_days"])).isoformat()
    
    # Find strong entity pairs
    pairs = conn.execute("""
        SELECT e1.name as source_name, e1.entity_type as source_type,
               e2.name as target_name, e2.entity_type as target_type,
               er.weight, er.last_seen
        FROM entity_relations er
        JOIN entities e1 ON er.source_id = e1.id
        JOIN entities e2 ON er.target_id = e2.id
        WHERE er.weight >= ?
          AND er.last_seen >= ?
        ORDER BY er.weight DESC
        LIMIT ?
    """, (config["min_entity_cooccurrence"], cutoff, config["max_patterns"])).fetchall()
    
    conn.close()
    
    patterns = []
    for sn, st, tn, tt, w, ls in pairs:
        patterns.append({
            "type": "entity_cooccurrence",
            "source": f"{sn} ({st})",
            "target": f"{tn} ({tt})",
            "weight": w,
            "last_seen": ls,
        })
    
    return patterns


def detect_debug_sessions(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Find sessions with high error rates in tool_calls.
    
    These indicate debugging sessions that might have useful info.
    """
    db_path = _get_sessions_db_path()
    conn = sqlite3.connect(db_path)
    
    cutoff = (datetime.now() - timedelta(days=config["lookback_days"])).isoformat()
    
    try:
        sessions = conn.execute("""
            SELECT tc.session_id, 
                   COUNT(*) as total_calls,
                   SUM(CASE WHEN tc.status = 'error' THEN 1 ELSE 0 END) as errors,
                   ROUND(100.0 * SUM(CASE WHEN tc.status = 'error' THEN 1 ELSE 0 END) / COUNT(*), 1) as error_pct,
                   GROUP_CONCAT(DISTINCT tc.tool_name) as tools
            FROM tool_calls tc
            JOIN sessions s ON tc.session_id = s.session_id
            WHERE s.created_at >= ?
            GROUP BY tc.session_id
            HAVING errors >= 3
            ORDER BY error_pct DESC
            LIMIT ?
        """, (cutoff, config["max_patterns"])).fetchall()
    except Exception:
        sessions = []
    
    conn.close()
    
    patterns = []
    for sid, total, errors, pct, tools in sessions:
        patterns.append({
            "type": "debug_session",
            "session_id": sid[:12],
            "total_calls": total,
            "errors": errors,
            "error_pct": pct,
            "tools": tools or "",
        })
    
    return patterns


async def trace(
    config: dict[str, Any] | None = None,
    save_memory_fn: Optional[Callable[[str, str], Awaitable[str]]] = None,
) -> dict[str, Any]:
    """Run all tracer detectors and return patterns found.
    
    Args:
        config: Override default config.
        save_memory_fn: Injected save function (key, value) → result string.
                        When provided, meaningful patterns are persisted to MEMORY.md.
    
    Returns:
        Dict with 'patterns' list and 'count' per type.
    """
    cfg = {**_DEFAULT_CONFIG, **(config or {})}
    dry = cfg["dry_run"]
    
    logger.info("Tracer %s (lookback: %d days)", "DRY RUN" if dry else "RUNNING", cfg["lookback_days"])
    
    patterns = []
    patterns.extend(detect_repeated_queries(cfg))
    patterns.extend(detect_entity_clusters(cfg))
    patterns.extend(detect_debug_sessions(cfg))
    
    by_type: dict[str, int] = {}
    for p in patterns:
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1
    
    logger.info("Found %d patterns: %s", len(patterns), by_type)
    
    # Save high-confidence patterns to MEMORY.md
    if save_memory_fn and patterns and not dry:
        saved_count = 0
        for p in patterns:
            key = None
            if p["type"] == "repeated_query" and p["times"] >= 5:
                key = f"patron:consulta-repetida-{p['query'][:30]}"
            elif p["type"] == "entity_cooccurrence" and p["weight"] >= 5:
                e1 = p["source"].split(" (")[0]
                e2 = p["target"].split(" (")[0]
                key = f"patron:entidades-{e1}-{e2}"
            elif p["type"] == "debug_session":
                key = f"checkpoint:sesion-debug-{p['session_id'][:8]}"
            if key:
                try:
                    await save_memory_fn(
                        key,
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | Tracer detected: {p['type']} — {p}"
                    )
                    saved_count += 1
                except Exception:
                    logger.exception("Failed to save tracer pattern: %s", key)
        logger.info("Saved %d/%d high-confidence patterns to MEMORY.md", saved_count, len(patterns))
    
    return {
        "patterns": patterns,
        "count_by_type": by_type,
        "total": len(patterns),
        "config": cfg,
    }


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    dry = "--dry" in sys.argv
    result = asyncio.run(trace({"dry_run": dry}))
    print(f"\n{'DRY RUN: ' if dry else ''}Found {result['total']} patterns:")
    for p in result["patterns"]:
        print(f"  [{p['type']}] {p}")
