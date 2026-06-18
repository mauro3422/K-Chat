"""Keyword search via vec_keywords table (TF-IDF)."""

from __future__ import annotations
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def keyword_search(
    query: str,
    db_path: str,
    top_k: int = 20,
    source_filter: str | None = None,
    exclude_source_key: str | None = None,
) -> list[tuple[int, float]]:
    """Search for exchanges matching query keywords.
    
    Extracts keywords from the query using TF-IDF, then searches
    the vec_keywords table for exchanges containing those keywords.
    
    Args:
        query: User query string.
        db_path: Path to memory.db.
        top_k: Maximum results to return.
        source_filter: Optional 'memory' or 'session' to filter by source.
        exclude_source_key: If set, exclude entries with this source_key.
    
    Returns:
        [(rowid, kw_score), ...] sorted by score descending.
        kw_score = sum of TF-IDF scores for matching keywords.
    """
    from src.memory.keywords.extractor import extract_keywords
    
    kws = extract_keywords(query, top_k=5)
    words = [w for w, _ in kws]
    
    if not words:
        return []
    
    placeholders = ",".join("?" for _ in words)
    params: list[Any] = [*words]
    
    source_join = ""
    source_where = ""
    if source_filter:
        source_join = "JOIN vec_meta m ON m.rowid = vk.rowid"
        source_where = "AND m.source = ?"
        params.append(source_filter)
    if exclude_source_key:
        if not source_join:
            source_join = "JOIN vec_meta m ON m.rowid = vk.rowid"
        source_where += " AND m.source_key != ?"
        params.append(exclude_source_key)
    
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT vk.rowid, SUM(vk.score) as score
            FROM vec_keywords vk
            {source_join}
            WHERE vk.word IN ({placeholders}) {source_where}
            GROUP BY vk.rowid
            ORDER BY score DESC
            LIMIT ?
            """,
            [*params, top_k]
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def keyword_search_batch(
    queries: list[str],
    db_path: str,
    top_k: int = 10,
) -> list[list[tuple[int, float]]]:
    """Run keyword_search for multiple queries.
    
    Useful for batch processing.
    """
    return [keyword_search(q, db_path, top_k) for q in queries]
