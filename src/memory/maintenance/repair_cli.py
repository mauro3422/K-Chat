"""CLI entry point for Kairos memory catalog repair."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.memory.maintenance.repair import (
    RepairReport,
    apply_catalog_repairs,
    plan_repairs,
    prune_stale_vectors,
    vectorize_missing,
)


def print_text_report(report: RepairReport, *, applied: bool) -> None:
    counts = report.counts
    print("Kairos memory repair")
    print(
        "planned: "
        f"catalog_embedded={counts.get('catalog_embedded', 0)} "
        f"catalog_memory_embedded={counts.get('catalog_memory_embedded', 0)} "
        f"catalog_deduped={counts.get('catalog_deduped', 0)} "
        f"catalog_noise={counts.get('catalog_noise', 0)} "
        f"orphan_catalog_row={counts.get('orphan_catalog_row', 0)} "
        f"missing_vector={counts.get('missing_vector', 0)} "
        f"stale_vector={counts.get('stale_vector', 0)} "
        f"broken_catalog_link={counts.get('broken_catalog_link', 0)}"
    )
    if applied:
        print(f"applied_catalog_rows={report.applied_catalog_rows}")
    if report.vectorized_sessions:
        print(f"vectorized_sessions={json.dumps(report.vectorized_sessions, sort_keys=True)}")
    if report.pruned_stale_vectors:
        print(f"pruned_stale_vectors={report.pruned_stale_vectors}")

    interesting = [
        a for a in report.actions
        if a.action in {"missing_vector", "stale_vector", "broken_catalog_link", "orphan_catalog_row"}
    ]
    if interesting:
        print("")
        print("Remaining work:")
        for action in interesting[:16]:
            rowid = f" rowid={action.vec_rowid}" if action.vec_rowid is not None else ""
            print(
                f"- {action.action}: {action.source_key}#{action.item_idx} "
                f"hash={action.content_hash[:12]}{rowid} {action.reason}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or apply safe Kairos memory catalog repairs.")
    parser.add_argument("--sessions-db", default="")
    parser.add_argument("--memory-db", default="")
    parser.add_argument("--apply", action="store_true", help="Write inferred catalog rows. Does not delete anything.")
    parser.add_argument(
        "--vectorize-missing",
        action="store_true",
        help="After --apply, explicitly generate vectors for sessions with missing vectors.",
    )
    parser.add_argument(
        "--prune-stale",
        action="store_true",
        help="After --apply, delete stale vector rowids detected by this repair plan.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if stale or missing vectors remain.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.vectorize_missing or args.prune_stale) and not args.apply:
        parser.error("--vectorize-missing and --prune-stale require --apply")

    sessions_db = args.sessions_db
    memory_db = args.memory_db
    if not sessions_db:
        from src.memory.db_path import resolve_db_path
        sessions_db = resolve_db_path()
    if not memory_db:
        from src.memory.memory_db_path import resolve_memory_db_path
        memory_db = resolve_memory_db_path()

    report = plan_repairs(sessions_db=sessions_db, memory_db=memory_db)
    if args.apply:
        applied_catalog_rows = apply_catalog_repairs(memory_db=memory_db, report=report)
        if applied_catalog_rows:
            report = plan_repairs(sessions_db=sessions_db, memory_db=memory_db)
        vectorized_sessions: dict[str, int] = {}
        pruned_stale_vectors = 0
        if args.vectorize_missing:
            vectorized_sessions = asyncio.run(vectorize_missing(report))
            report = plan_repairs(sessions_db=sessions_db, memory_db=memory_db)
        if args.prune_stale:
            pruned_stale_vectors = prune_stale_vectors(memory_db=memory_db, report=report)
            report = plan_repairs(sessions_db=sessions_db, memory_db=memory_db)
        report.applied_catalog_rows = applied_catalog_rows
        report.vectorized_sessions = vectorized_sessions
        report.pruned_stale_vectors = pruned_stale_vectors

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report, applied=args.apply)

    if args.strict and (
        report.counts.get("missing_vector", 0)
        or report.counts.get("stale_vector", 0)
        or report.counts.get("broken_catalog_link", 0)
        or report.counts.get("orphan_catalog_row", 0)
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
