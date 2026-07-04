"""Tool: daily_memory_report - build the morning memory work plan."""

from __future__ import annotations

import json
from datetime import date
from typing import Any


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "daily_memory_report",
        "description": (
            "Build or preview the morning memory report from inbox items, "
            "curator candidates, curation reports, and daily synthesis artifacts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": "Optional project root. Defaults to Kairos project root.",
                    "default": "",
                },
                "date": {
                    "type": "string",
                    "description": "Optional target date YYYY-MM-DD.",
                    "default": "",
                },
                "write": {
                    "type": "boolean",
                    "description": "When true, write memory/plans/morning/YYYY/MM/DD.md.",
                    "default": True,
                },
                "preflight": {
                    "type": "boolean",
                    "description": "When true, include local memory preflight in dry-run mode. Defaults to true for the daily operational report.",
                    "default": True,
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "description": "Output format for preview/result payload.",
                    "default": "markdown",
                },
                "compact": {
                    "type": "boolean",
                    "description": "When format=json, return the compact operational payload for daily automations.",
                    "default": False,
                },
                "laptop_status_json": {
                    "type": "string",
                    "description": "Optional path to a laptop health JSON object.",
                    "default": "",
                },
                "laptop_status_command": {
                    "type": "string",
                    "description": "Optional command that prints laptop health as a JSON object.",
                    "default": "",
                },
                "laptop_status_timeout": {
                    "type": "integer",
                    "description": "Seconds to wait for laptop_status_command before reporting timeout.",
                    "default": 45,
                },
            },
        },
    },
}


def _target_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    return date.fromisoformat(raw)


async def run(**kwargs) -> str:
    root = str(kwargs.get("root") or "").strip() or None
    target = _target_date(str(kwargs.get("date") or ""))
    should_write = bool(kwargs.get("write", True))
    include_preflight = bool(kwargs.get("preflight", True))
    output_format = str(kwargs.get("format") or "markdown").strip().lower()
    compact = bool(kwargs.get("compact", False))
    laptop_status_json = str(kwargs.get("laptop_status_json") or "").strip() or None
    laptop_status_command = str(kwargs.get("laptop_status_command") or "").strip() or None
    laptop_status_timeout = max(1, int(kwargs.get("laptop_status_timeout") or 45))

    try:
        from src.memory.synthesis.morning_plan import (
            build_morning_plan,
            render_morning_plan_json,
            render_morning_plan,
            write_morning_plan,
        )

        if should_write:
            path = write_morning_plan(
                root=root,
                target_date=target,
                include_preflight=include_preflight,
                laptop_status_json=laptop_status_json,
                laptop_status_command=laptop_status_command,
                laptop_status_timeout=laptop_status_timeout,
            )
            if output_format == "json":
                plan = build_morning_plan(
                    root=root,
                    target_date=target,
                    include_preflight=include_preflight,
                    laptop_status_json=laptop_status_json,
                    laptop_status_command=laptop_status_command,
                    laptop_status_timeout=laptop_status_timeout,
                )
                from src.memory.synthesis.morning_plan import compact_morning_plan

                return json.dumps(
                    {"ok": True, "path": str(path), "plan": compact_morning_plan(plan) if compact else plan},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            return f"[OK] Daily memory report written to `{path}`."

        plan = build_morning_plan(
            root=root,
            target_date=target,
            include_preflight=include_preflight,
            laptop_status_json=laptop_status_json,
            laptop_status_command=laptop_status_command,
            laptop_status_timeout=laptop_status_timeout,
        )
        if output_format == "json":
            return render_morning_plan_json(plan, compact=compact)
        return render_morning_plan(plan)
    except Exception as exc:
        return f"[ERROR] daily_memory_report failed: {exc}"
