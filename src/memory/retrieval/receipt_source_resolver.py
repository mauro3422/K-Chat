"""Resolve persisted memory receipt sources from an injected memory database."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryReceiptSourceResolver:
    """Load the vector row referenced by a receipt without global configuration."""

    def __init__(self, db_path: str) -> None:
        self._db_path = str(Path(db_path).resolve())

    @staticmethod
    def _matches_receipt(row: sqlite3.Row, receipt: dict[str, Any]) -> bool:
        if str(row["source"] or "") != str(receipt.get("source") or ""):
            return False
        if str(row["source_key"] or "") != str(receipt.get("source_key") or ""):
            return False
        if int(row["exchange_idx"] or 0) != int(receipt.get("item_idx", 0)):
            return False
        expected_hash = str(receipt.get("content_hash") or "")
        return not expected_hash or str(row["content_hash"] or "") == expected_hash

    def load_vector_source(self, receipt: dict[str, Any]) -> dict[str, Any]:
        """Load a receipt row, validating its stable identity before returning it."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = None
            vec_rowid = receipt.get("vec_rowid")
            if vec_rowid is not None:
                row = conn.execute(
                    """
                    SELECT rowid, source, source_key, exchange_idx, text, metadata,
                           created_at, content_hash
                    FROM vec_meta
                    WHERE rowid=?
                    """,
                    (int(vec_rowid),),
                ).fetchone()
                if row is not None and not self._matches_receipt(row, receipt):
                    row = None
            if row is None:
                content_hash = str(receipt.get("content_hash") or "")
                hash_clause = " AND content_hash=?" if content_hash else ""
                parameters: tuple[Any, ...] = (
                    receipt.get("source", ""),
                    receipt.get("source_key", ""),
                    int(receipt.get("item_idx", 0)),
                )
                if content_hash:
                    parameters += (content_hash,)
                row = conn.execute(
                    f"""
                    SELECT rowid, source, source_key, exchange_idx, text, metadata,
                           created_at, content_hash
                    FROM vec_meta
                    WHERE source=? AND source_key=? AND exchange_idx=?
                    {hash_clause}
                    ORDER BY rowid DESC
                    LIMIT 1
                    """,
                    parameters,
                ).fetchone()
            return dict(row) if row else {}
        except sqlite3.Error:
            logger.info("Vector source unavailable while hydrating memory receipt", exc_info=True)
            return {}
        finally:
            conn.close()


__all__ = ["MemoryReceiptSourceResolver"]
