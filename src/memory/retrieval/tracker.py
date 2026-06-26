"""Track retrieval queries for analysis and dedup."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)


def track_retrieval(
    db_path: str,
    query: str,
    result_count: int,
    method: str = "hybrid",
    source_filter: str | None = None,
) -> None:
    """Log a retrieval query summary to the retrieval_log table for analysis.

    Uses the existing retrieval_log table schema which stores per-result rows.
    Logs a summary row with vec_rowid=0 as a query-level marker.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Log a summary row (vec_rowid=0 signals this is a query marker, not a result)
        conn.execute(
            "INSERT INTO retrieval_log (session_id, query, vec_rowid, fusion_score, relevance_score, rank, source) "
            "VALUES (?, ?, 0, 0.0, 0.0, 0, ?)",
            ("", query[:500], f"{method}|{result_count}"),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to track retrieval")
