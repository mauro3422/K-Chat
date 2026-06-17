"""Hydrate retrieval results — convert row IDs to full result objects."""

from __future__ import annotations

import sqlite3
from typing import Any


def hydrate_results(
    results: list[tuple[int, float]],
    conn: Any,
    top_k: int,
) -> list[dict[str, Any]]:
    """Convert (rowid, score) tuples to full result dicts with metadata."""
    # Ensure Row factory for dict-like access
    if hasattr(conn, 'row_factory'):
        conn.row_factory = sqlite3.Row
    hydrated = []
    for rowid, score in results[:top_k]:
        row = conn.execute(
            "SELECT source, source_key, text, created_at, metadata, relevance_score "
            "FROM vec_meta WHERE rowid = ?",
            (rowid,),
        ).fetchone()
        if row is None:
            continue
        hydrated.append({
            "rowid": rowid,
            "source": row["source"],
            "source_key": row["source_key"],
            "text": row["text"],
            "created_at": row["created_at"],
            "metadata": row["metadata"],
            "relevance_score": row["relevance_score"],
            "score": score,
        })
    return hydrated
