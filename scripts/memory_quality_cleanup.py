"""Plan or apply conservative cleanup of legacy curated memories."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._python_bootstrap import ensure_repo_python
from src.memory.maintenance.quality_cleanup import (
    apply_quality_cleanup,
    load_memory_rows,
    plan_quality_cleanup_state,
)
from src.memory.operations._helpers import _parse_memory_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize legacy timestamps and remove disposable memory probes."
    )
    parser.add_argument("--memory-db", default="")
    parser.add_argument("--memory-file", default="")
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply and not args.confirm:
        raise SystemExit("--apply requires --confirm")

    if args.memory_db:
        memory_db = Path(args.memory_db)
    else:
        from src.memory.memory_db_path import resolve_memory_db_path

        memory_db = Path(resolve_memory_db_path())
    memory_file = Path(args.memory_file) if args.memory_file else ROOT / "MEMORY.md"
    backup_dir = (
        Path(args.backup_dir)
        if args.backup_dir
        else ROOT.parent / f"{ROOT.name}-local-archive" / "memory-quality"
    )

    db_rows = load_memory_rows(str(memory_db))
    file_memories = _parse_memory_md(str(memory_file))
    file_timestamp = datetime.fromtimestamp(memory_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    plan = plan_quality_cleanup_state(
        db_rows,
        file_memories,
        file_updated_at=file_timestamp,
    )
    payload: dict[str, object] = {"applied": False, "plan": plan.as_dict()}
    if args.apply:
        payload["result"] = apply_quality_cleanup(
            memory_db=str(memory_db),
            memory_file=str(memory_file),
            backup_dir=str(backup_dir),
            plan=plan,
        )
        payload["applied"] = True

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "Kairos memory quality cleanup: "
            f"updates={len(plan.updates)} deletes={len(plan.deletes)} "
            f"migrations={len(plan.migrations)} conflicts={len(plan.conflicts)}"
        )
        if args.apply:
            print(json.dumps(payload["result"], ensure_ascii=False, sort_keys=True))
    return 2 if plan.conflicts else 0


if __name__ == "__main__":
    ensure_repo_python(__file__, command_name="scripts/memory_quality_cleanup.py")
    raise SystemExit(main())
