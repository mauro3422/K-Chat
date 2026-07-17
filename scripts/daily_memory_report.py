"""Generate the Kairos morning memory work plan."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.synthesis.morning_plan import (
    build_morning_plan,
    render_morning_plan,
    render_morning_plan_json,
    write_morning_plan,
)


def _configure_utf8_stdout() -> None:
    """Keep report output portable on Windows consoles."""

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _configure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Generate morning memory plan from curator artifacts.")
    parser.add_argument("--root", default=str(ROOT), help="Project root.")
    parser.add_argument("--date", default="", help="Target date YYYY-MM-DD.")
    parser.add_argument("--preview", action="store_true", help="Print without writing the artifact.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--compact-json", action="store_true", help="When used with --json, print a compact operational payload.")
    parser.add_argument(
        "--preflight",
        dest="preflight",
        action="store_true",
        default=True,
        help="Include local memory preflight in dry-run mode (default).",
    )
    parser.add_argument(
        "--no-preflight",
        dest="preflight",
        action="store_false",
        help="Skip local memory preflight for a faster lightweight report.",
    )
    parser.add_argument("--laptop-status-json", default="", help="Path to a laptop health JSON object.")
    parser.add_argument("--laptop-status-command", default="", help="Command that prints laptop health as JSON.")
    parser.add_argument("--laptop-status-timeout", type=int, default=45, help="Seconds to wait for laptop health command.")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else None
    if args.preview:
        plan = build_morning_plan(
            root=args.root,
            target_date=target,
            include_preflight=args.preflight,
            laptop_status_json=args.laptop_status_json or None,
            laptop_status_command=args.laptop_status_command or None,
            laptop_status_timeout=max(1, args.laptop_status_timeout),
        )
        print(render_morning_plan_json(plan, compact=args.compact_json) if args.json else render_morning_plan(plan))
        return 0

    path = write_morning_plan(
        root=args.root,
        target_date=target,
        include_preflight=args.preflight,
        laptop_status_json=args.laptop_status_json or None,
        laptop_status_command=args.laptop_status_command or None,
        laptop_status_timeout=max(1, args.laptop_status_timeout),
    )
    if args.json:
        plan = build_morning_plan(
            root=args.root,
            target_date=target,
            include_preflight=args.preflight,
            laptop_status_json=args.laptop_status_json or None,
            laptop_status_command=args.laptop_status_command or None,
            laptop_status_timeout=max(1, args.laptop_status_timeout),
        )
        payload = render_morning_plan_json(plan, compact=args.compact_json)
        print(json.dumps({"ok": True, "path": str(path), "plan": json.loads(payload)}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
