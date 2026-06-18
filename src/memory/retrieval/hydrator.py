"""Hydrate retrieval results — convert row IDs to full result objects."""

from __future__ import annotations

import sqlite3
from typing import Any


def _vec_meta_columns(conn: Any) -> set[str]:
    try:
        rows = conn.execute("PRAGMA table_info(vec_meta)").fetchall()
    except Exception:
        return set()
    return {row[1] if isinstance(row, tuple) else row["name"] for row in rows}


def hydrate_results(
    results: list[tuple[int, float]],
    conn: Any,
    top_k: int,
) -> list[dict[str, Any]]:
    """Convert (rowid, score) tuples to full result dicts with metadata."""
    # Ensure Row factory for dict-like access
    if hasattr(conn, 'row_factory'):
        conn.row_factory = sqlite3.Row
    columns = _vec_meta_columns(conn)
    select_cols = ["source", "source_key", "text"]
    for optional in ("created_at", "metadata", "relevance_score"):
        if optional in columns:
            select_cols.append(optional)
    hydrated = []
    for rowid, score in results[:top_k]:
        row = conn.execute(
            f"SELECT {', '.join(select_cols)} FROM vec_meta WHERE rowid = ?",
            (rowid,),
        ).fetchone()
        if row is None:
            continue
        created_at = row["created_at"] if "created_at" in row.keys() else None
        metadata = row["metadata"] if "metadata" in row.keys() else None
        relevance_score = row["relevance_score"] if "relevance_score" in row.keys() else score
        hydrated.append({
            "rowid": rowid,
            "source": row["source"],
            "source_key": row["source_key"],
            "text": row["text"],
            "created_at": created_at,
            "metadata": metadata,
            "relevance_score": relevance_score,
            "score": score,
        })
    return hydrated
