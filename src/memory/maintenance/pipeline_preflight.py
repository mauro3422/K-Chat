#!/usr/bin/env python
"""Run memory catalog backfill and audit across Kairos nodes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.maintenance.backfill_processing_catalog import run_backfill
from src.memory.maintenance.audit import run_audit
from src.memory.maintenance.repair import apply_catalog_repairs, plan_repairs
from src.memory.health_contract import normalize_health_status, worst_health_status


class RemoteCommandRunner(Protocol):
    def run_json(self, command: str, *, timeout: int) -> dict[str, Any]:
        """Run a remote command and return its JSON payload."""


@dataclass(frozen=True)
class ProcessRemoteRunner:
    """Small adapter for SSH-like commands.

    The command prefix is injected by callers so this module stays independent
    from the remote client implementation.
    """

    command_prefix: list[str]

    def run_json(self, command: str, *, timeout: int) -> dict[str, Any]:
        result = subprocess.run(
            [*self.command_prefix, command],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            if result.returncode != 0:
                raise RuntimeError(_remote_error(result.returncode, result.stdout, result.stderr)) from exc
            raise RuntimeError(f"remote returned non-JSON output: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("remote returned JSON that is not an object")
        payload.setdefault("command_exit_code", result.returncode)
        if result.returncode != 0:
            payload.setdefault("remote_error", _remote_error(result.returncode, result.stdout, result.stderr))
        return payload


def _remote_error(returncode: int, stdout: str, stderr: str) -> str:
    parts = [f"remote exit={returncode}"]
    if stdout.strip():
        parts.append(f"stdout={stdout.strip()[:600]}")
    if stderr.strip():
        parts.append(f"stderr={stderr.strip()[:600]}")
    return " ".join(parts)


def _resolve_paths(*, sessions_db: str, memory_db: str, root: str) -> tuple[str, str, str]:
    resolved_root = root or str(ROOT)
    resolved_sessions = sessions_db
    resolved_memory = memory_db
    if not resolved_sessions:
        from src.memory.db_path import resolve_db_path

        resolved_sessions = resolve_db_path()
    if not resolved_memory:
        from src.memory.memory_db_path import resolve_memory_db_path

        resolved_memory = resolve_memory_db_path()
    return resolved_sessions, resolved_memory, resolved_root


def node_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    counts = report.get("counts", {})
    processing = report.get("processing_catalog", {})
    summary = report.get("summary", {})
    health = report.get("health", {})
    integrity = health.get("integrity", {})
    coverage = health.get("coverage", {})
    quality = health.get("quality", {})
    return {
        "status": normalize_health_status(report.get("status"), legacy_ok=report.get("ok")),
        "integrity_status": normalize_health_status(integrity.get("status"), legacy_ok=report.get("ok")),
        "coverage_status": normalize_health_status(coverage.get("status")),
        "quality_status": normalize_health_status(quality.get("status")),
        "sessions": int(counts.get("sessions", 0)),
        "messages": int(counts.get("messages", 0)),
        "memory_entries": int(counts.get("memory_index", 0)),
        "vectors": int(counts.get("memory_vec_meta", 0)),
        "vector_sources": dict(report.get("vector_sources", {})),
        "catalog_total": int(report.get("catalog", {}).get("total", 0)),
        "catalog_statuses": dict(report.get("catalog", {}).get("by_status", {})),
        "processing_total": int(processing.get("total", 0)),
        "processing_stages": dict(processing.get("by_stage_status", {})),
        "missing_sessions": int(summary.get("sessions_with_missing_vectors", 0)),
        "stale_sessions": int(summary.get("sessions_with_stale_vectors", 0)),
        "orphan_sources": int(summary.get("orphan_vector_sources", 0)),
        "processing_failed": int(summary.get("processing_failed", 0)),
        "processing_stale": int(summary.get("processing_stale", 0)),
        "duplicates": dict(report.get("duplicates", {})),
        "synthesis_count": int(report.get("synthesis", {}).get("count", 0)),
        "transversal_synthesis_count": int(
            report.get("synthesis", {}).get("transversal", {}).get("count", 0)
        ),
    }


def node_issues(report: dict[str, Any]) -> list[str]:
    health = report.get("health", {})
    integrity = health.get("integrity", {}) if isinstance(health, dict) else {}
    if isinstance(integrity, dict) and integrity:
        return [str(item) for item in integrity.get("issues", []) if str(item).strip()]

    # Compatibility fallback for audit payloads older than contract v2.
    issues: list[str] = []
    summary = report.get("summary", {})
    processing = report.get("processing_catalog", {})
    catalog = report.get("catalog", {})
    if not report.get("ok", False):
        issues.append("memory_audit reported inconsistent state")
    if not catalog.get("exists", False):
        issues.append("memory_work_catalog is missing")
    if not processing.get("exists", False):
        issues.append("memory_processing_catalog is missing")
    if int(summary.get("sessions_with_stale_vectors", 0)) > 0:
        issues.append(f"stale session vectors={summary.get('sessions_with_stale_vectors')}")
    if int(summary.get("orphan_vector_sources", 0)) > 0:
        issues.append(f"orphan vector sources={summary.get('orphan_vector_sources')}")
    if int(summary.get("processing_failed", 0)) > 0:
        issues.append(f"processing failed={summary.get('processing_failed')}")
    if int(summary.get("processing_stale", 0)) > 0:
        issues.append(f"processing stale={summary.get('processing_stale')}")
    if int(processing.get("stale", 0)) > 0:
        stale_rows = processing.get("stale_rows", [])
        if stale_rows:
            first = stale_rows[0]
            issues.append(f"first stale processing row={first.get('stage')} {first.get('source')}:{first.get('source_key')}")
    return issues


def _dimension_issues(report: dict[str, Any], dimension: str) -> list[str]:
    health = report.get("health", {})
    payload = health.get(dimension, {}) if isinstance(health, dict) else {}
    if not isinstance(payload, dict):
        return []
    return [str(item) for item in payload.get("issues", []) if str(item).strip()]


def run_local_pipeline(
    *,
    node: str,
    sessions_db: str = "",
    memory_db: str = "",
    root: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved_sessions, resolved_memory, resolved_root = _resolve_paths(
        sessions_db=sessions_db,
        memory_db=memory_db,
        root=root,
    )
    try:
        repair_report = plan_repairs(sessions_db=resolved_sessions, memory_db=resolved_memory)
        if not dry_run:
            repair_report.applied_catalog_rows = apply_catalog_repairs(
                memory_db=resolved_memory,
                report=repair_report,
            )
        backfill = run_backfill(
            sessions_db=resolved_sessions,
            memory_db=resolved_memory,
            root=Path(resolved_root),
            dry_run=dry_run,
        )
        audit = run_audit(
            sessions_db=resolved_sessions,
            memory_db=resolved_memory,
            root=resolved_root,
        )
        issues = node_issues(audit)
        attention = _dimension_issues(audit, "coverage")
        warnings = _dimension_issues(audit, "quality")
        ok = bool(audit.get("ok", False)) and not issues
        status = normalize_health_status(audit.get("status"), legacy_ok=ok)
        if not ok:
            status = "error"
        return {
            "node": node,
            "ok": ok,
            "status": status,
            "error": "",
            "repair": repair_report.as_dict(),
            "backfill": backfill,
            "audit": audit,
            "snapshot": node_snapshot(audit),
            "issues": issues,
            "attention": attention,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "node": node,
            "ok": False,
            "status": "error",
            "error": str(exc),
            "repair": {},
            "backfill": {},
            "audit": {},
            "snapshot": {},
            "issues": [str(exc)],
            "attention": [],
            "warnings": [],
        }


def run_remote_pipeline(
    *,
    node: str,
    runner: RemoteCommandRunner,
    timeout: int = 120,
    dry_run: bool = False,
) -> dict[str, Any]:
    args = ["scripts/memory_pipeline_preflight.py", "--local-only", "--json", "--node-name", node]
    if dry_run:
        args.append("--dry-run")
    command = " ".join(_shell_quote(part) for part in args)
    try:
        payload = runner.run_json(command, timeout=timeout)
    except Exception as exc:
        return {
            "node": node,
            "ok": False,
            "status": "error",
            "error": str(exc),
            "backfill": {},
            "audit": {},
            "snapshot": {},
            "issues": [str(exc)],
            "attention": [],
            "warnings": [],
        }
    return payload


def _shell_quote(value: str) -> str:
    if not value:
        return "''"
    safe = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:-")
    if all(char in safe for char in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def compare_snapshots(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(nodes) < 2:
        return []
    base = nodes[0]
    base_snapshot = base.get("snapshot", {})
    comparisons: list[dict[str, Any]] = []
    for node in nodes[1:]:
        snapshot = node.get("snapshot", {})
        differences: dict[str, Any] = {}
        for key in (
            "sessions",
            "messages",
            "memory_entries",
            "vectors",
            "catalog_total",
            "processing_total",
            "synthesis_count",
            "transversal_synthesis_count",
            "vector_sources",
            "catalog_statuses",
            "processing_stages",
        ):
            left = base_snapshot.get(key)
            right = snapshot.get(key)
            if left != right:
                differences[key] = {
                    str(base.get("node", "base")): left,
                    str(node.get("node", "node")): right,
                }
        comparisons.append({
            "base": base.get("node", "base"),
            "node": node.get("node", "node"),
            "differences": differences,
        })
    return comparisons


def build_pipeline_report(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons = compare_snapshots(nodes)
    failed = [node for node in nodes if not node.get("ok", False)]
    statuses = [
        normalize_health_status(node.get("status"), legacy_ok=node.get("ok"))
        for node in nodes
    ]
    if any(comparison.get("differences") for comparison in comparisons):
        statuses.append("attention")
    return {
        "ok": not failed,
        "status": worst_health_status(statuses),
        "nodes": nodes,
        "comparisons": comparisons,
        "failed_nodes": [node.get("node", "") for node in failed],
    }


def print_short_report(report: dict[str, Any]) -> None:
    nodes = report.get("nodes", [])
    passed = len([node for node in nodes if node.get("ok", False)])
    print(f"Kairos memory pipeline preflight: {passed}/{len(nodes)} nodes consistent")
    for node in nodes:
        snapshot = node.get("snapshot", {})
        backfill = node.get("backfill", {})
        status = normalize_health_status(node.get("status"), legacy_ok=node.get("ok")).upper()
        print(
            f"[{status}] {node.get('node')}: "
            f"sessions={snapshot.get('sessions', 0)} vectors={snapshot.get('vectors', 0)} "
            f"processing={snapshot.get('processing_total', 0)} "
            f"backfill_sessions={backfill.get('sessions_observed', 0)} "
            f"backfill_synthesis={backfill.get('daily_synthesis_processed', 0)}"
        )
        for issue in node.get("issues", [])[:4]:
            print(f"  - {issue}")
        for item in node.get("attention", [])[:4]:
            print(f"  - attention: {item}")
        for warning in node.get("warnings", [])[:4]:
            print(f"  - warning: {warning}")
    for comparison in report.get("comparisons", []):
        differences = comparison.get("differences", {})
        if not differences:
            print(f"[MATCH] {comparison.get('base')} vs {comparison.get('node')}: no snapshot differences")
            continue
        print(f"[DIFF] {comparison.get('base')} vs {comparison.get('node')}: {len(differences)} fields differ")
        for key, values in list(differences.items())[:8]:
            print(f"  - {key}: {json.dumps(values, ensure_ascii=False, sort_keys=True)}")
    if report.get("status") == "error":
        print("Inconsistent memory pipeline state remains after backfill.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Kairos memory backfill and audit preflight.")
    parser.add_argument("--node-name", default="local")
    parser.add_argument("--sessions-db", default="")
    parser.add_argument("--memory-db", default="")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--local-only", action="store_true", help="Run only this node. Remote orchestration is provided by ops/remote/kairos_remote.py.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    local = run_local_pipeline(
        node=args.node_name,
        sessions_db=args.sessions_db,
        memory_db=args.memory_db,
        root=args.root,
        dry_run=args.dry_run,
    )
    report = build_pipeline_report([local])
    if args.json:
        print(json.dumps(local if args.local_only else report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_short_report(report)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
