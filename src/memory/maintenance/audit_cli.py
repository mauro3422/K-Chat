"""CLI entry point for the Kairos memory audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.memory.maintenance.audit import run_audit, SessionAudit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only audit of Kairos memory embeddings and synthesis state.")
    parser.add_argument("--sessions-db", default="")
    parser.add_argument("--memory-db", default="")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def print_text_report(report: dict[str, Any]) -> None:
    counts = report["counts"]
    summary = report["summary"]
    print("Kairos memory audit")
    print(f"sessions={counts['sessions']} messages={counts['messages']} memory_entries={counts['memory_index']}")
    print(f"vectors={counts['memory_vec_meta']} sources={json.dumps(report['vector_sources'], sort_keys=True)}")
    catalog = report["catalog"]
    if catalog["exists"]:
        print(
            "catalog: "
            f"units={catalog['total']} statuses={json.dumps(catalog['by_status'], sort_keys=True)} "
            f"pending={catalog['pending']} missing_vec_links={catalog['missing_vec_links']} "
            f"uncataloged_vectors={catalog['uncataloged_vectors']}"
        )
    processing = report["processing_catalog"]
    if processing["exists"]:
        print(
            "processing: "
            f"units={processing['total']} stages={json.dumps(processing['by_stage_status'], sort_keys=True)} "
            f"pending={processing['pending']} failed={processing['failed']} stale={processing['stale']}"
        )
    quality = report["curated_memory_quality"]
    if quality["exists"]:
        print(
            "curated_quality: "
            f"empty={quality['empty']} too_short={quality['too_short']} "
            f"missing_timestamp={quality['missing_timestamp']} "
            f"low_signal={quality['low_signal']} vague={quality['vague']} "
            f"probe={quality['probe']} avg_score={quality['avg_quality_score']} "
            f"duplicate_value_groups={quality['duplicate_value_groups']}"
        )
    print(
        "issues: "
        f"missing_sessions={summary['sessions_with_missing_vectors']} "
        f"stale_sessions={summary['sessions_with_stale_vectors']} "
        f"orphan_sources={summary['orphan_vector_sources']} "
        f"dup_hash_groups={report['duplicates']['hash_groups']} "
        f"dup_content_hash_groups={report['duplicates']['content_hash_groups']} "
        f"processing_failed={summary['processing_failed']} "
        f"processing_stale={summary['processing_stale']} "
        f"curated_empty={summary['curated_empty']}"
    )
    if report["legacy"]["sessions_db_has_vec_meta"]:
        print(f"legacy: sessions.db has vec_meta with {report['legacy']['sessions_db_vec_meta_count']} rows")

    synthesis = report["synthesis"]
    print(f"synthesis: exists={synthesis['exists']} count={synthesis['count']} latest={synthesis['latest'] or '-'}")

    printed = False
    for session in report["sessions"]:
        if not session["missing_hashes"] and not session["stale_vectors"]:
            continue
        if not printed:
            print("")
            print("Session issues:")
            printed = True
        label = session["name"] or session["session_id"][:12]
        print(
            f"- {label}: exchanges={session['exchange_count']} vectors={session['vector_count']} "
            f"missing={len(session['missing_hashes'])} stale={len(session['stale_vectors'])}"
        )
        if session["missing_hashes"]:
            print(f"  missing: {', '.join(session['missing_hashes'][:8])}")
        if session["stale_vectors"]:
            stale = ", ".join(f"{item['exchange_idx']}:{item['hash']}" for item in session["stale_vectors"][:8])
            print(f"  stale: {stale}")

    if report["orphan_vectors"]:
        print("")
        print("Orphan vectors:")
        for item in report["orphan_vectors"][:12]:
            print(f"- {item['source_key']}: count={item['count']} max_exchange_idx={item['max_exchange_idx']}")

    if processing.get("stale_rows"):
        print("")
        print("Processing catalog stale rows:")
        for item in processing["stale_rows"][:12]:
            print(
                f"- {item['stage']} {item['source']}:{item['source_key']} "
                f"hash={item['hash']} expected={item['expected_hash']} status={item['status']}"
            )

    if quality.get("samples"):
        print("")
        print("Curated memory quality samples:")
        for item in quality["samples"][:12]:
            if item["kind"] == "duplicate_value":
                print(f"- duplicate_value: {', '.join(item['keys'])}")
            else:
                print(f"- {item['kind']}: {item['key']}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sessions_db = args.sessions_db
    memory_db = args.memory_db
    if not sessions_db:
        from src.memory.db_path import resolve_db_path
        sessions_db = resolve_db_path()
    if not memory_db:
        from src.memory.memory_db_path import resolve_memory_db_path
        memory_db = resolve_memory_db_path()

    report = run_audit(sessions_db=sessions_db, memory_db=memory_db, root=args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
