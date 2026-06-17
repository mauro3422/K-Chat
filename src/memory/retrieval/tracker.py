"""Track retrieval queries for analysis and dedup."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)


def track_retrieval(
    db_path: str,
    query: str,
    result_count: int,
    method: str = "hybrid",
    source_filter: str | None = None,
) -> None:
    """Log a retrieval query to the retrieval_log table for analysis."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO retrieval_log (query, result_count, method, source_filter, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (query[:500], result_count, method, source_filter, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("Failed to track retrieval")
