#!/usr/bin/env python
"""Backfill semantic processing catalog rows without re-running LLM work."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.content_hash import content_hash
from src.memory.db_path import resolve_db_path
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _curation_candidate_hash(sessions_conn: sqlite3.Connection, memory_conn: sqlite3.Connection, session_id: str) -> tuple[str, int]:
    session = sessions_conn.execute(
        "SELECT name FROM sessions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if session is None:
        return "", 0
    rows = memory_conn.execute(
        """
        SELECT text
        FROM vec_meta
        WHERE source='session'
          AND source_key=?
          AND length(text) > 30
        ORDER BY exchange_idx DESC
        LIMIT 8
        """,
        (session_id,),
    ).fetchall()
    texts = [str(row["text"]) for row in rows if str(row["text"] or "")]
    if not texts:
        return "", 0
    prompt = (
        f"Session: {str(session['name'] or '') or session_id[:12]}\n\n"
        + "\n---\n".join(text[:400] for text in texts)
        + "\n\nExtract new info or NO_NEW_INFO"
    )
    return content_hash(prompt), len(texts)


def backfill_session_candidates(
    *,
    sessions_db: str,
    memory_db: str,
    catalog: MemoryProcessingCatalogRepository,
    dry_run: bool,
) -> int:
    sessions_conn = _connect(sessions_db)
    memory_conn = _connect(memory_db)
    try:
        if not _table_exists(sessions_conn, "sessions") or not _table_exists(memory_conn, "vec_meta"):
            return 0
        rows = memory_conn.execute(
            """
            SELECT source_key, COUNT(1) AS vector_count
            FROM vec_meta
            WHERE source='session'
            GROUP BY source_key
            """
        ).fetchall()
        count = 0
        for row in rows:
            session_id = str(row["source_key"])
            digest, text_count = _curation_candidate_hash(sessions_conn, memory_conn, session_id)
            if not digest:
                continue
            count += 1
            if dry_run:
                continue
            catalog.mark(
                source="session",
                source_key=session_id,
                item_idx=-1,
                stage="curation_candidate",
                content_hash=digest,
                status="observed",
                processor="backfill_processing_catalog",
                reason="vectorized_session_seen",
                metadata={"texts": text_count, "vectors": int(row["vector_count"])},
            )
        return count
    finally:
        sessions_conn.close()
        memory_conn.close()


def backfill_daily_synthesis(
    *,
    root: Path,
    catalog: MemoryProcessingCatalogRepository,
    dry_run: bool,
) -> int:
    synthesis_root = root / "memory" / "synthesis"
    if not synthesis_root.exists():
        return 0
    count = 0
    for report_path in sorted(synthesis_root.glob("*/*/*.md")):
        year = report_path.parent.parent.name
        month = report_path.parent.name
        day = report_path.stem
        date_str = f"{year}-{month}-{day}"
        text = report_path.read_text(encoding="utf-8", errors="replace")
        count += 1
        if dry_run:
            continue
        catalog.mark(
            source="daily_synthesis",
            source_key=date_str,
            item_idx=-1,
            stage="generated",
            content_hash=content_hash(text, limit=100000),
            status="processed",
            processor="backfill_processing_catalog",
            reason="existing_report_seen",
            metadata={"path": str(report_path.relative_to(root))},
        )
    return count


def run_backfill(*, sessions_db: str, memory_db: str, root: Path, dry_run: bool) -> dict[str, Any]:
    catalog = MemoryProcessingCatalogRepository(memory_db)
    sessions = backfill_session_candidates(
        sessions_db=sessions_db,
        memory_db=memory_db,
        catalog=catalog,
        dry_run=dry_run,
    )
    reports = backfill_daily_synthesis(root=root, catalog=catalog, dry_run=dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "sessions_observed": sessions,
        "daily_synthesis_processed": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill memory_processing_catalog from existing derived artifacts.")
    parser.add_argument("--sessions-db", default=resolve_db_path())
    parser.add_argument("--memory-db", default=resolve_memory_db_path())
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_backfill(
        sessions_db=args.sessions_db,
        memory_db=args.memory_db,
        root=Path(args.root),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
