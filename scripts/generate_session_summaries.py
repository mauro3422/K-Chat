"""Generate extractive Kairos session summaries."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.db_path import resolve_db_path
from src.memory.synthesis.session import (
    generate_session_summaries,
    generate_session_summary_candidates,
    vectorize_session_summary_artifacts,
)
from src.memory.synthesis.daily import generate_daily_synthesis
from src.memory.synthesis.transversal import (
    generate_transversal_synthesis_candidates,
    generate_transversal_synthesis,
    vectorize_transversal_synthesis_artifacts,
)
from src.memory.curator.curation_events import write_curation_report
from src.memory.curator.candidate_workbench import vectorize_memory_candidates
from src.memory.curator.memory_inbox import vectorize_memory_inbox_items


def _configure_utf8_stdio() -> None:
    """Keep JSON/CLI output portable on Windows consoles."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _pipeline_curation_report(
    *,
    root: str,
    target: date | None,
    summaries: list[dict[str, Any]],
    embedding: dict[str, Any] | None,
    candidates: dict[str, Any] | None,
    transversal: dict[str, Any] | None,
    transversal_candidates: dict[str, Any] | None,
    transversal_embedding: dict[str, Any] | None,
    candidate_embedding: dict[str, Any] | None,
    inbox_embedding: dict[str, Any] | None,
    daily_synthesis: str | None,
) -> str:
    """Write a lightweight curation artifact for the morning pipeline."""

    report_date = target.isoformat() if target else date.today().isoformat()
    metadata = {
        "source": "generate_session_summaries",
        "date": report_date,
        "session_summaries": len(summaries),
        "session_summary_embeddings": (embedding or {}).get("embedded", 0),
        "session_summary_candidates": (candidates or {}).get("created", 0),
        "transversal_generated": bool(transversal),
        "transversal_session_count": (transversal or {}).get("session_count", 0),
        "transversal_candidates": (transversal_candidates or {}).get("created", 0),
        "transversal_embeddings": (transversal_embedding or {}).get("embedded", 0),
        "memory_candidate_embeddings": (candidate_embedding or {}).get("embedded", 0),
        "memory_inbox_embeddings": (inbox_embedding or {}).get("embedded", 0),
        "daily_synthesis": bool(daily_synthesis),
    }
    lines = [
        f"# Morning Memory Pipeline - {report_date}",
        "",
        "## Summary",
        f"- Session summaries generated/checked: {len(summaries)}",
        f"- Session summary candidates created: {metadata['session_summary_candidates']}",
        f"- Transversal synthesis: {'yes' if transversal else 'no'}",
        f"- Transversal sessions: {metadata['transversal_session_count']}",
        f"- Transversal candidates created: {metadata['transversal_candidates']}",
        f"- Memory candidate embeddings: {metadata['memory_candidate_embeddings']}",
        f"- Memory inbox embeddings: {metadata['memory_inbox_embeddings']}",
        f"- Daily synthesis: {'yes' if daily_synthesis else 'no'}",
    ]
    if daily_synthesis:
        lines.append(f"- Daily synthesis artifact: `{daily_synthesis}`")
    if transversal and transversal.get("path"):
        lines.append(f"- Transversal artifact: `{transversal.get('path')}`")
    if candidates and candidates.get("path"):
        lines.append(f"- Session candidates artifact: `{candidates.get('path')}`")
    if transversal_candidates and transversal_candidates.get("path"):
        lines.append(f"- Transversal candidates artifact: `{transversal_candidates.get('path')}`")
    path = write_curation_report(
        lines,
        metadata,
        root=root,
        timestamp=f"{report_date}T09:00:00",
    )
    return str(path)


def main() -> int:
    _configure_utf8_stdio()

    parser = argparse.ArgumentParser(description="Generate per-session memory summaries.")
    parser.add_argument("--db", default="", help="Path to sessions.db. Defaults to configured Kairos DB.")
    parser.add_argument("--root", default=str(ROOT), help="Project root for artifacts.")
    parser.add_argument("--date", default="", help="Target date YYYY-MM-DD.")
    parser.add_argument("--embed", action="store_true", help="Embed session summary artifacts after generation.")
    parser.add_argument("--candidates", action="store_true", help="Create reviewable memory candidates from summaries.")
    parser.add_argument("--transversal", action="store_true", help="Generate cross-session transversal synthesis.")
    parser.add_argument("--transversal-candidates", action="store_true", help="Create reviewable memory candidates from transversal synthesis.")
    parser.add_argument("--embed-transversal", action="store_true", help="Embed transversal synthesis artifacts.")
    parser.add_argument("--embed-candidates", action="store_true", help="Embed reviewable memory candidates.")
    parser.add_argument("--embed-inbox", action="store_true", help="Embed daily memory inbox items.")
    parser.add_argument("--daily-synthesis", action="store_true", help="Generate the daily synthesis artifact after summaries.")
    parser.add_argument("--curation-report", action="store_true", help="Write a lightweight morning pipeline curation report artifact.")
    parser.add_argument("--json", action="store_true", help="Print generated summaries as JSON.")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else None
    db_path = args.db or resolve_db_path()
    results = asyncio.run(generate_session_summaries(db_path, root=args.root, target_date=target))
    embedding_result = None
    if args.embed:
        embedding_result = asyncio.run(vectorize_session_summary_artifacts(root=args.root))
    candidate_result = None
    if args.candidates:
        candidate_result = generate_session_summary_candidates(root=args.root, target_date=target)
    transversal_result = None
    if args.transversal:
        transversal_result = generate_transversal_synthesis(root=args.root, target_date=target)
    transversal_candidate_result = None
    if args.transversal_candidates:
        transversal_candidate_result = generate_transversal_synthesis_candidates(root=args.root, target_date=target)
    transversal_embedding_result = None
    if args.embed_transversal:
        transversal_embedding_result = asyncio.run(vectorize_transversal_synthesis_artifacts(root=args.root))
    candidate_embedding_result = None
    if args.embed_candidates:
        candidate_embedding_result = asyncio.run(vectorize_memory_candidates(root=args.root))
    inbox_embedding_result = None
    if args.embed_inbox:
        inbox_embedding_result = asyncio.run(vectorize_memory_inbox_items(root=args.root))
    daily_synthesis_result = None
    if args.daily_synthesis:
        daily_synthesis_result = asyncio.run(
            generate_daily_synthesis(db_path, root=args.root, target_date=target)
        )
    curation_report_result = None
    if args.curation_report:
        curation_report_result = _pipeline_curation_report(
            root=args.root,
            target=target,
            summaries=results,
            embedding=embedding_result,
            candidates=candidate_result,
            transversal=transversal_result,
            transversal_candidates=transversal_candidate_result,
            transversal_embedding=transversal_embedding_result,
            candidate_embedding=candidate_embedding_result,
            inbox_embedding=inbox_embedding_result,
            daily_synthesis=daily_synthesis_result,
        )
    if args.json:
        print(json.dumps(
            {
                "ok": True,
                "count": len(results),
                "summaries": results,
                "embedding": embedding_result,
                "candidates": candidate_result,
                "transversal": transversal_result,
                "transversal_candidates": transversal_candidate_result,
                "transversal_embedding": transversal_embedding_result,
                "candidate_embedding": candidate_embedding_result,
                "inbox_embedding": inbox_embedding_result,
                "daily_synthesis": daily_synthesis_result,
                "curation_report": curation_report_result,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        for item in results:
            marker = "updated" if item.get("changed") else "unchanged"
            print(f"{marker}: {item.get('path')}")
        if embedding_result is not None:
            print(f"embedding: {embedding_result}")
        if candidate_result is not None:
            print(f"candidates: {candidate_result}")
        if transversal_result is not None:
            print(f"transversal: {transversal_result}")
        if transversal_candidate_result is not None:
            print(f"transversal_candidates: {transversal_candidate_result}")
        if transversal_embedding_result is not None:
            print(f"transversal_embedding: {transversal_embedding_result}")
        if candidate_embedding_result is not None:
            print(f"candidate_embedding: {candidate_embedding_result}")
        if inbox_embedding_result is not None:
            print(f"inbox_embedding: {inbox_embedding_result}")
        if daily_synthesis_result is not None:
            print(f"daily_synthesis: {daily_synthesis_result}")
        if curation_report_result is not None:
            print(f"curation_report: {curation_report_result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
