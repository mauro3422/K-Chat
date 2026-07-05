"""Morning plan report built from memory inbox and curator artifacts."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from src.memory import paths as memory_paths
from src.memory.curator.candidate_workbench import list_candidate_cards
from src.memory.curator.curation_queue import build_curation_queue
from src.memory.curator.curation_events import load_curation_decisions
from src.memory.curator.memory_inbox import load_memory_inbox


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _base(root: str | Path | None = None) -> Path:
    return Path(root) if root is not None else _project_root()


def morning_plan_path(
    target_date: date | str | None = None,
    root: str | Path | None = None,
) -> Path:
    """Return the daily morning plan artifact path.

    New location: ``memory/YYYY/MM/DD/morning-plan.md``.
    """
    return memory_paths.morning_plan_path(target=target_date, root=root)


def _default_target_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    if current.hour < 4:
        return (current - timedelta(days=1)).date()
    return current.date()


def _load_latest_markdown(root: str | Path | None, filename: str) -> tuple[Path | None, str]:
    """Find the most recent Markdown artifact in ``memory/*/*/*/{filename}``."""

    base = _base(root) / "memory"
    if not base.exists():
        return None, ""
    files = sorted(base.glob(f"*/*/*/{filename}"), reverse=True)
    if not files:
        return None, ""
    path = files[0]
    return path, path.read_text(encoding="utf-8")


def _extract_metadata_comment(text: str) -> dict[str, Any]:
    marker = "<!-- metadata:"
    if marker not in text:
        return {}
    tail = text.split(marker, 1)[1]
    raw = tail.split("-->", 1)[0].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _line_preview(text: str, limit: int = 8) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("<!--"):
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _filter_items_for_date(items: list[dict[str, Any]], target: date) -> list[dict[str, Any]]:
    target_str = target.isoformat()
    return [
        item for item in items
        if str(item.get("created_at", "")).startswith(target_str)
    ]


def _filter_decisions_for_date(items: list[dict[str, Any]], target: date) -> list[dict[str, Any]]:
    target_str = target.isoformat()
    return [
        item for item in items
        if str(item.get("created_at", "")).startswith(target_str)
    ]


def _inbox_group_key(item: Mapping[str, Any]) -> tuple[str, str]:
    key = " ".join(str(item.get("key") or "").split()).lower()
    value = " ".join(str(item.get("value") or "").split()).lower()
    return key, value


def coalesce_inbox_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group repeated inbox facts while preserving source ids for audit."""

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        group_key = _inbox_group_key(item)
        if not any(group_key):
            group_key = (str(item.get("inbox_id") or ""), "")
        current = groups.get(group_key)
        created_at = str(item.get("created_at") or "")
        artifact = str(item.get("_artifact") or item.get("artifact") or "")
        if current is None:
            current = {
                "group_id": str(item.get("inbox_id") or ""),
                "key": item.get("key", ""),
                "value": item.get("value", ""),
                "status": item.get("status", "pending"),
                "urgency": item.get("urgency", "normal"),
                "source": item.get("source", ""),
                "channel": item.get("channel", ""),
                "session_id": item.get("session_id", ""),
                "message_ref": item.get("message_ref", ""),
                "first_seen": created_at,
                "last_seen": created_at,
                "reinforcement_count": 0,
                "inbox_ids": [],
                "artifacts": [],
                "items": [],
            }
            groups[group_key] = current

        current["reinforcement_count"] = int(current.get("reinforcement_count") or 0) + 1
        if created_at:
            first_seen = str(current.get("first_seen") or created_at)
            last_seen = str(current.get("last_seen") or created_at)
            current["first_seen"] = min(first_seen, created_at)
            current["last_seen"] = max(last_seen, created_at)
        inbox_id = str(item.get("inbox_id") or "")
        if inbox_id and inbox_id not in current["inbox_ids"]:
            current["inbox_ids"].append(inbox_id)
        if artifact and artifact not in current["artifacts"]:
            current["artifacts"].append(artifact)
        current["items"].append(dict(item))
        if _priority_for_inbox(item) > _priority_for_inbox(current):
            current["urgency"] = item.get("urgency", current.get("urgency", "normal"))

    return sorted(
        groups.values(),
        key=lambda item: (
            _priority_for_inbox(item),
            int(item.get("reinforcement_count") or 0),
            str(item.get("last_seen") or ""),
        ),
        reverse=True,
    )


def _run_command(args: list[str], cwd: Path, timeout: int = 8) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except Exception as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def git_health(root: str | Path | None = None) -> dict[str, Any]:
    """Collect a lightweight local git health snapshot."""

    repo_root = _base(root)
    code, branch_out, branch_err = _run_command(["git", "status", "--short", "--branch"], repo_root)
    if code != 0:
        return {
            "available": False,
            "branch": "",
            "ahead": 0,
            "behind": 0,
            "dirty": False,
            "changed": 0,
            "untracked": 0,
            "stashes": 0,
            "warnings": [branch_err or "git status failed"],
        }

    lines = branch_out.splitlines()
    branch_line = lines[0] if lines else ""
    branch = branch_line.removeprefix("## ").split("...")[0].strip()
    ahead = _parse_branch_counter(branch_line, "ahead")
    behind = _parse_branch_counter(branch_line, "behind")
    changed_lines = lines[1:]
    untracked = sum(1 for line in changed_lines if line.startswith("??"))
    changed = len(changed_lines)
    stash_code, stash_out, _ = _run_command(["git", "stash", "list"], repo_root)
    stashes = len([line for line in stash_out.splitlines() if line.strip()]) if stash_code == 0 else 0

    warnings: list[str] = []
    if changed:
        warnings.append(f"working tree has {changed} changed paths")
    if untracked:
        warnings.append(f"untracked paths={untracked}")
    if ahead:
        warnings.append(f"branch ahead={ahead}")
    if behind:
        warnings.append(f"branch behind={behind}")
    if stashes:
        warnings.append(f"stashes={stashes}")

    return {
        "available": True,
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "dirty": changed > 0,
        "changed": changed,
        "untracked": untracked,
        "stashes": stashes,
        "warnings": warnings,
    }


def _parse_branch_counter(branch_line: str, label: str) -> int:
    marker = f"{label} "
    if marker not in branch_line:
        return 0
    tail = branch_line.split(marker, 1)[1]
    raw = tail.split(",", 1)[0].split("]", 1)[0].strip()
    try:
        return int(raw)
    except ValueError:
        return 0


def preflight_health(root: str | Path | None = None) -> dict[str, Any]:
    """Run local memory preflight in dry-run mode."""

    try:
        from src.memory.maintenance.pipeline_preflight import run_local_pipeline

        return run_local_pipeline(node="local", root=str(_base(root)), dry_run=True)
    except Exception as exc:
        return {
            "node": "local",
            "ok": False,
            "error": str(exc),
            "issues": [str(exc)],
            "snapshot": {},
        }


def _normalize_laptop_status(payload: Mapping[str, Any], source: str) -> dict[str, Any]:
    warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
    warnings.extend(_doctor_payload_warnings(payload))
    status = str(payload.get("status") or "").strip()
    if not status:
        status = "ok" if payload.get("ok") is True else "degraded" if payload.get("ok") is False else "unknown"
    available = bool(payload.get("available", status not in {"not_configured", "unknown", "error"}))
    normalized = dict(payload)
    normalized["checks"] = _compact_laptop_checks(payload.get("checks"))
    normalized.update(
        {
            "available": available,
            "status": status,
            "source": source,
            "warnings": warnings,
        }
    )
    return normalized


def _compact_laptop_checks(checks: Any, *, text_limit: int = 420) -> Any:
    if not isinstance(checks, list):
        return checks
    compacted: list[Any] = []
    for check in checks:
        if not isinstance(check, Mapping):
            compacted.append(check)
            continue
        row = dict(check)
        for field in ("stdout", "stderr"):
            if field in row:
                row[field] = _truncate_text(str(row.get(field) or ""), text_limit)
        compacted.append(row)
    return compacted


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [truncated {len(value) - limit} chars]"


def _doctor_payload_warnings(payload: Mapping[str, Any]) -> list[str]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return []
    warnings: list[str] = []
    for check in checks:
        if not isinstance(check, Mapping) or check.get("ok") is True:
            continue
        name = str(check.get("name") or "unknown")
        detail = str(check.get("detail") or "failed")
        hint = str(check.get("hint") or "").strip()
        warning = f"{name}: {detail}"
        if hint:
            warning = f"{warning} ({hint})"
        warnings.append(warning)
    return warnings


def laptop_remediation_commands(laptop: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return safe follow-up commands for laptop health failures."""

    failed = [
        item for item in laptop.get("failed_checks") or []
        if isinstance(item, Mapping)
    ]
    for check in laptop.get("checks") or []:
        if isinstance(check, Mapping) and check.get("ok") is not True:
            failed.append(check)

    commands: list[dict[str, str]] = []
    names = {str(item.get("name") or "") for item in failed}
    if "memory_audit" in names:
        commands.extend(
            [
                {
                    "kind": "diagnose",
                    "label": "Remote memory audit detail",
                    "command": (
                        "python ops\\remote\\kairos_remote.py kairos-python "
                        "--node laptop --command \"scripts/memory_audit.py --json\""
                    ),
                },
                {
                    "kind": "preview",
                    "label": "Remote memory repair plan",
                    "command": (
                        "python ops\\remote\\kairos_remote.py kairos-python "
                        "--node laptop --command \"scripts/memory_repair.py --json\""
                    ),
                },
                {
                    "kind": "manual_apply",
                    "label": "Remote repair apply, manual only",
                    "command": (
                        "python ops\\remote\\kairos_remote.py kairos-python "
                        "--node laptop --command \"scripts/memory_repair.py --apply --vectorize-missing --prune-stale --json\""
                    ),
                },
            ]
        )
    if not commands and str(laptop.get("status") or "") in {"degraded", "error", "unknown"}:
        commands.append(
            {
                "kind": "diagnose",
                "label": "Remote doctor detail",
                "command": "python ops\\remote\\kairos_remote.py doctor --node laptop --json",
            }
        )
    return commands


def _parse_laptop_command_payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["command_exit_code"] = result.returncode
    if result.returncode != 0 and result.stderr.strip():
        warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
        warnings.append(f"stderr: {result.stderr.strip()[:400]}")
        payload["warnings"] = warnings
    return payload


def laptop_health(
    root: str | Path | None = None,
    status_json: str | Path | None = None,
    command: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Collect laptop health from a configured JSON file or command."""

    configured_file = status_json or os.getenv("KAIROS_LAPTOP_STATUS_JSON", "")
    if configured_file:
        path = Path(configured_file)
        if not path.is_absolute():
            path = _base(root) / path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "available": False,
                "status": "error",
                "source": str(path),
                "warnings": [f"laptop status json failed: {exc}"],
            }
        if not isinstance(payload, Mapping):
            return {
                "available": False,
                "status": "error",
                "source": str(path),
                "warnings": ["laptop status json must contain an object"],
            }
        return _normalize_laptop_status(payload, str(path))

    configured_command = command or os.getenv("KAIROS_LAPTOP_STATUS_COMMAND", "")
    if configured_command:
        try:
            result = subprocess.run(
                configured_command,
                cwd=str(_base(root)),
                text=True,
                capture_output=True,
                timeout=timeout,
                shell=True,
            )
        except Exception as exc:
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": [f"laptop status command failed: {exc}"],
            }
        payload = _parse_laptop_command_payload(result)
        if payload is not None:
            return _normalize_laptop_status(payload, "command")
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or f"exit={result.returncode}"
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": [f"laptop status command failed: {stderr}"],
            }
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": [f"laptop status command returned invalid json: {exc}"],
            }
        if not isinstance(payload, Mapping):
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": ["laptop status command must return a JSON object"],
            }
        return _normalize_laptop_status(payload, "command")

    return {
        "available": False,
        "status": "not_configured",
        "source": "",
        "warnings": ["laptop health is not configured in this local report"],
    }


def build_health(
    root: str | Path | None = None,
    include_preflight: bool = False,
    laptop_status_json: str | Path | None = None,
    laptop_status_command: str | None = None,
    laptop_status_timeout: int = 45,
) -> dict[str, Any]:
    """Build local operational health for the morning report."""

    health = {
        "git": git_health(root=root),
        "preflight": {},
        "laptop": laptop_health(
            root=root,
            status_json=laptop_status_json,
            command=laptop_status_command,
            timeout=laptop_status_timeout,
        ),
    }
    if include_preflight:
        health["preflight"] = preflight_health(root=root)
    return health


def _priority_for_inbox(item: Mapping[str, Any]) -> int:
    urgency = str(item.get("urgency") or "normal").lower()
    if urgency == "high":
        return 90
    if urgency == "low":
        return 35
    return 60


def _priority_for_candidate(card: Mapping[str, Any]) -> int:
    score = float(card.get("score") or 0.0)
    missing = card.get("metadata_missing") or []
    base = int(score * 100)
    if missing:
        return max(base, 65)
    return base


def _priority_for_ready_candidate(card: Mapping[str, Any]) -> int:
    return max(88, _priority_for_candidate(card))


def memory_pipeline_status(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize memory pipeline readiness for the daily plan."""

    pending_inbox = len(plan.get("pending_inbox") or [])
    inbox_groups = len(plan.get("inbox_groups") or [])
    pending_candidates = len(plan.get("candidate_cards") or [])
    ready_candidates = len(plan.get("ready_candidate_cards") or [])
    decisions = len(plan.get("curation_decisions") or [])
    curation = plan.get("curation_report") or {}
    synthesis = plan.get("daily_synthesis") or {}
    transversal = plan.get("transversal_synthesis") or {}
    transversal_metadata = transversal.get("metadata") or {}
    curation_metadata = curation.get("metadata") or {}
    health = plan.get("health") or {}
    git = health.get("git") or {}
    preflight = health.get("preflight") or {}
    laptop = health.get("laptop") or {}

    issues: list[str] = []
    next_steps: list[str] = []

    if ready_candidates:
        next_steps.append(f"promote {ready_candidates} ready candidate(s)")
    if pending_candidates:
        next_steps.append(f"review {pending_candidates} pending candidate(s)")
    if inbox_groups:
        next_steps.append(f"curate {inbox_groups} inbox group(s)")
    if pending_inbox and not inbox_groups:
        next_steps.append(f"inspect {pending_inbox} pending inbox item(s)")

    if not curation.get("path"):
        issues.append("no curation report found")
    if not synthesis.get("path"):
        issues.append("no daily synthesis found")
    if not transversal.get("path"):
        issues.append("no transversal synthesis found")
    transversal_session_count = int(transversal_metadata.get("session_count") or 0)
    transversal_expected = any(
        int(curation_metadata.get(key) or 0) > 0
        for key in (
            "session_summaries",
            "session_summary_candidates",
            "session_summary_embeddings",
            "transversal_candidates",
        )
    )
    if transversal.get("path") and transversal_session_count == 0 and transversal_expected:
        issues.append("transversal synthesis has no sessions")

    if git.get("dirty"):
        issues.append(f"working tree dirty ({git.get('changed', 0)} changed paths)")
    if int(git.get("behind") or 0) > 0:
        issues.append(f"branch behind by {git.get('behind')} commit(s)")
    if int(git.get("stashes") or 0) > 0:
        issues.append(f"{git.get('stashes')} stash(es) pending")

    if preflight and not preflight.get("ok", False):
        issues.append("memory preflight has issues")
    if laptop.get("status") in {"not_configured", "error", "unknown", "degraded"}:
        issues.append(f"laptop health {laptop.get('status', 'unknown')}")

    if not next_steps:
        next_steps.append("no memory curation actions pending")

    blocking = [
        issue for issue in issues
        if "preflight" in issue or "branch behind" in issue or "laptop health error" in issue
    ]
    if blocking:
        status = "blocked"
    elif issues or next_steps != ["no memory curation actions pending"]:
        status = "attention"
    else:
        status = "ok"

    return {
        "status": status,
        "pending_inbox": pending_inbox,
        "inbox_groups": inbox_groups,
        "pending_candidates": pending_candidates,
        "ready_candidates": ready_candidates,
        "curation_decisions": decisions,
        "issues": issues,
        "next_steps": next_steps,
    }


def relation_decision_summaries(
    decisions: list[Mapping[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Extract relation-focused decisions for curator review."""

    summaries: list[dict[str, Any]] = []
    for decision in decisions:
        action = str(decision.get("action") or "")
        kind = str(decision.get("kind") or "")
        if kind == "memory_relation" or action in {"upsert_relation", "materialize_hints"}:
            if decision.get("source_id") and decision.get("target_id"):
                summaries.append(
                    {
                        "action": action,
                        "kind": kind,
                        "source_id": decision.get("source_id", ""),
                        "target_id": decision.get("target_id", ""),
                        "relation_type": decision.get("relation_type", ""),
                        "weight": decision.get("weight", ""),
                        "evidence": str(decision.get("evidence") or decision.get("reason") or "")[:220],
                        "curated_relation_id": decision.get("curated_relation_id", ""),
                        "artifact": decision.get("_artifact") or decision.get("artifact", ""),
                        "explain_command": _relation_explain_command(
                            relation_id=str(decision.get("curated_relation_id") or ""),
                            source_id=str(decision.get("source_id") or ""),
                            target_id=str(decision.get("target_id") or ""),
                            relation_type=str(decision.get("relation_type") or ""),
                            candidate_id=str(decision.get("candidate_id") or ""),
                        ),
                    }
                )
                if len(summaries) >= limit:
                    return summaries
            continue

        hints = decision.get("relation_hints") or []
        if not isinstance(hints, list):
            continue
        for hint in hints:
            if not isinstance(hint, Mapping):
                continue
            summaries.append(
                {
                    "action": action,
                    "kind": kind,
                    "source_id": hint.get("source_id", ""),
                    "target_id": hint.get("target_id", ""),
                    "relation_type": hint.get("relation_type", ""),
                    "weight": hint.get("weight", decision.get("reinforcement_count", "")),
                    "evidence": str(decision.get("value") or decision.get("query") or decision.get("reason") or "")[:220],
                    "curated_relation_id": decision.get("curated_relation_id", ""),
                    "artifact": decision.get("_artifact") or decision.get("artifact", ""),
                    "explain_command": _relation_explain_command(
                        relation_id=str(decision.get("curated_relation_id") or ""),
                        source_id=str(hint.get("source_id") or ""),
                        target_id=str(hint.get("target_id") or ""),
                        relation_type=str(hint.get("relation_type") or ""),
                        candidate_id=str(decision.get("candidate_id") or decision.get("group_id") or ""),
                    ),
                }
            )
            if len(summaries) >= limit:
                return summaries
    return summaries


def curation_feedback_summary(decisions: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Summarize curator outcomes by source layer for future weight tuning."""

    buckets: dict[str, dict[str, Any]] = {}
    positive_actions = {"promote", "promote_ready", "upsert_relation", "materialize_hints"}
    negative_actions = {"reject"}
    blocked_actions = {"needs_metadata", "complete_metadata"}

    for decision in decisions:
        source = str(decision.get("source") or decision.get("candidate_source") or "").strip()
        kind = str(decision.get("kind") or "").strip()
        action = str(decision.get("action") or "").strip()
        if not source:
            source = _feedback_source_from_kind(kind)
        if not source:
            source = "unknown"

        bucket = buckets.setdefault(
            source,
            {
                "source": source,
                "total": 0,
                "positive": 0,
                "negative": 0,
                "blocked": 0,
                "actions": {},
                "relation_types": {},
                "suggested_adjustment": "hold",
            },
        )
        bucket["total"] += 1
        bucket["actions"][action or "unknown"] = int(bucket["actions"].get(action or "unknown", 0)) + 1
        relation_type = str(decision.get("relation_type") or "").strip()
        if relation_type:
            bucket["relation_types"][relation_type] = int(bucket["relation_types"].get(relation_type, 0)) + 1
        if action in positive_actions:
            bucket["positive"] += 1
        elif action in negative_actions:
            bucket["negative"] += 1
        elif action in blocked_actions:
            missing = decision.get("missing_fields") or []
            if action == "complete_metadata" and not missing:
                bucket["positive"] += 1
            else:
                bucket["blocked"] += 1

    summaries: list[dict[str, Any]] = []
    for bucket in buckets.values():
        total = int(bucket["total"] or 0)
        positive = int(bucket["positive"] or 0)
        negative = int(bucket["negative"] or 0)
        blocked = int(bucket["blocked"] or 0)
        if total:
            positive_rate = round(positive / total, 3)
            negative_rate = round(negative / total, 3)
            blocked_rate = round(blocked / total, 3)
        else:
            positive_rate = negative_rate = blocked_rate = 0.0
        if total >= 3 and positive_rate >= 0.67:
            adjustment = "consider_raise"
        elif total >= 3 and (negative_rate + blocked_rate) >= 0.67:
            adjustment = "consider_lower"
        else:
            adjustment = "hold"
        bucket["positive_rate"] = positive_rate
        bucket["negative_rate"] = negative_rate
        bucket["blocked_rate"] = blocked_rate
        bucket["suggested_adjustment"] = adjustment
        summaries.append(bucket)

    return sorted(
        summaries,
        key=lambda item: (str(item.get("suggested_adjustment") or ""), int(item.get("total") or 0)),
        reverse=True,
    )


def retrieval_weight_recommendations(
    feedback: list[Mapping[str, Any]],
    *,
    current_weights: Mapping[str, float] | None = None,
    step: float = 0.04,
) -> list[dict[str, Any]]:
    """Translate curation feedback into conservative retrieval weight proposals."""

    weights = dict(current_weights or _default_source_layer_weights())
    source_map = {
        "remember": "memory_candidate",
        "memory_candidate": "memory_candidate",
        "transversal_synthesis": "transversal_synthesis",
        "session_summary": "session_summary",
        "memory_inbox": "memory_inbox",
        "curated_relation": "memory",
    }
    recommendations: list[dict[str, Any]] = []
    for item in feedback:
        source = str(item.get("source") or "")
        layer = source_map.get(source, source)
        if layer not in weights:
            continue
        current = float(weights[layer])
        adjustment = str(item.get("suggested_adjustment") or "hold")
        total = int(item.get("total") or 0)
        if adjustment == "consider_raise":
            proposed = min(1.0, current + step)
            rationale = "positive curator outcomes dominate"
        elif adjustment == "consider_lower":
            proposed = max(0.1, current - step)
            rationale = "rejections or metadata blocks dominate"
        else:
            proposed = current
            rationale = "insufficient or mixed curator signal"
        recommendations.append(
            {
                "source": source,
                "layer": layer,
                "current_weight": round(current, 3),
                "proposed_weight": round(proposed, 3),
                "delta": round(proposed - current, 3),
                "sample_size": total,
                "suggested_adjustment": adjustment,
                "rationale": rationale,
                "apply_policy": "manual_review_required",
            }
        )
    return recommendations


def _default_source_layer_weights() -> dict[str, float]:
    try:
        from src.memory.retrieval.source_policy import default_weights

        return default_weights()
    except Exception:
        return {
            "memory": 1.0,
            "session": 0.82,
            "session_summary": 0.9,
            "transversal_synthesis": 0.94,
            "memory_candidate": 0.78,
            "memory_inbox": 0.72,
        }


def _feedback_source_from_kind(kind: str) -> str:
    if kind == "memory_inbox":
        return "memory_inbox"
    if kind == "memory_candidate":
        return "memory_candidate"
    if kind == "memory_relation":
        return "curated_relation"
    return ""


def _relation_explain_command(
    *,
    relation_id: str = "",
    source_id: str = "",
    target_id: str = "",
    relation_type: str = "",
    candidate_id: str = "",
) -> str:
    if relation_id:
        return f"curator_workbench action=explain_relation relation_id={relation_id}"
    if source_id and target_id and relation_type:
        command = (
            "curator_workbench action=explain_relation "
            f"source_id={source_id} target_id={target_id} relation_type={relation_type}"
        )
        if candidate_id:
            command = f"{command} candidate_id={candidate_id}"
        return command
    return ""


def _queue_item_id_for_command(action: Mapping[str, Any]) -> str:
    item_id = str(action.get("id") or "").strip()
    if item_id:
        return item_id
    for field in ("recommended_command", "followup_command", "fallback_command"):
        command = str(action.get(field) or "")
        for marker in ("group_id=", "candidate_id="):
            if marker not in command:
                continue
            raw = command.split(marker, 1)[1].split()[0].strip()
            return raw.strip('"').strip("'")
    return ""


def memory_layer_pipeline_command(target_date: date | str) -> str:
    """Return the daily command that prepares memory layers before curation."""

    date_str = target_date.isoformat() if isinstance(target_date, date) else str(target_date)
    return (
        "python scripts\\generate_session_summaries.py "
        f"--date {date_str} "
        "--embed --candidates --transversal --transversal-candidates "
        "--embed-transversal --embed-candidates --embed-inbox "
        "--daily-synthesis --curation-report --json"
    )


def morning_report_command(target_date: date | str) -> str:
    """Return the compact morning report command for the given date."""

    date_str = target_date.isoformat() if isinstance(target_date, date) else str(target_date)
    return (
        "python scripts\\daily_memory_report.py "
        f"--date {date_str} --preview --preflight "
        "--laptop-status-command \"python ops\\remote\\kairos_remote.py doctor --node laptop --json\" "
        "--laptop-status-timeout 60 --json --compact-json"
    )


def build_morning_plan(
    root: str | Path | None = None,
    target_date: date | None = None,
    inbox_limit: int = 30,
    candidate_limit: int = 30,
    include_preflight: bool = False,
    laptop_status_json: str | Path | None = None,
    laptop_status_command: str | None = None,
    laptop_status_timeout: int = 45,
) -> dict[str, Any]:
    """Collect artifacts and build a deterministic morning work plan."""

    target = target_date or _default_target_date()
    inbox_items = _filter_items_for_date(load_memory_inbox(root=root, limit=inbox_limit * 4), target)
    pending_inbox = [
        item for item in inbox_items
        if str(item.get("status", "pending")) == "pending"
    ][:inbox_limit]
    inbox_groups = coalesce_inbox_items(pending_inbox)
    candidate_cards = list_candidate_cards(root=root, status="pending", limit=candidate_limit)
    ready_candidate_cards = list_candidate_cards(
        root=root,
        status="ready_for_promotion",
        limit=candidate_limit,
    )
    synthesis_path, synthesis_text = _load_latest_markdown(root, "daily.md")
    transversal_path, transversal_text = _load_latest_markdown(root, "transversal.md")
    curation_path, curation_text = _load_latest_markdown(root, "events/curation.md")
    curation_metadata = _extract_metadata_comment(curation_text)
    transversal_metadata = _extract_metadata_comment(transversal_text)
    curation_decisions = _filter_decisions_for_date(load_curation_decisions(root=root, limit=50), target)

    actions = build_curation_queue(
        inbox_groups=inbox_groups,
        candidate_cards=candidate_cards,
        ready_candidate_cards=ready_candidate_cards,
        curation_decisions=curation_decisions,
    )
    curation_feedback = curation_feedback_summary(curation_decisions)
    weight_recommendations = retrieval_weight_recommendations(curation_feedback)
    weight_policy_draft = _build_weight_policy_draft(weight_recommendations, root=root)
    plan = {
        "date": target.isoformat(),
        "pending_inbox": pending_inbox,
        "inbox_groups": inbox_groups,
        "candidate_cards": candidate_cards,
        "ready_candidate_cards": ready_candidate_cards,
        "curation_report": {
            "path": str(curation_path) if curation_path else "",
            "metadata": curation_metadata,
            "preview": _line_preview(curation_text),
        },
        "curation_decisions": curation_decisions,
        "relation_decisions": relation_decision_summaries(curation_decisions),
        "curation_feedback": curation_feedback,
        "weight_recommendations": weight_recommendations,
        "weight_policy_draft": weight_policy_draft,
        "daily_synthesis": {
            "path": str(synthesis_path) if synthesis_path else "",
            "preview": _line_preview(synthesis_text, limit=10),
        },
        "transversal_synthesis": {
            "path": str(transversal_path) if transversal_path else "",
            "metadata": transversal_metadata,
            "preview": _line_preview(transversal_text, limit=10),
        },
        "health": build_health(
            root=root,
            include_preflight=include_preflight,
            laptop_status_json=laptop_status_json,
            laptop_status_command=laptop_status_command,
            laptop_status_timeout=laptop_status_timeout,
        ),
        "actions": actions,
        "pipeline_commands": {
            "prepare_layers": memory_layer_pipeline_command(target),
            "compact_report": morning_report_command(target),
            "runbook": "curator_workbench action=runbook",
            "runbook_top": "curator_workbench action=runbook item_id=top",
        },
    }
    plan["pipeline_status"] = memory_pipeline_status(plan)
    return plan


def _build_weight_policy_draft(
    recommendations: list[Mapping[str, Any]],
    root: str | Path | None = None,
) -> dict[str, Any]:
    actionable = [item for item in recommendations if float(item.get("delta") or 0.0) != 0.0]
    if not actionable:
        return {}
    try:
        from src.memory.retrieval.source_policy import build_weight_policy_draft

        return build_weight_policy_draft(actionable, root=root)
    except Exception:
        return {}


def compact_morning_plan(plan: Mapping[str, Any], *, action_limit: int = 12) -> dict[str, Any]:
    """Return a compact operational JSON payload for daily automations."""

    health = plan.get("health") or {}
    git = health.get("git") if isinstance(health.get("git"), Mapping) else {}
    laptop = health.get("laptop") if isinstance(health.get("laptop"), Mapping) else {}
    preflight = health.get("preflight") if isinstance(health.get("preflight"), Mapping) else {}
    failed_laptop_checks = [
        dict(item)
        for item in laptop.get("failed_checks") or []
        if isinstance(item, Mapping)
    ]
    for check in laptop.get("checks") or []:
        if not isinstance(check, Mapping) or check.get("ok") is True:
            continue
        failed_laptop_checks.append(
            {
                "name": check.get("name", ""),
                "detail": check.get("detail", ""),
                "hint": check.get("hint", ""),
            }
        )

    actions = []
    for action in list(plan.get("actions") or [])[:action_limit]:
        item_id = _queue_item_id_for_command(action)
        row = {
            "priority": action.get("priority", 0),
            "kind": action.get("kind", ""),
            "id": item_id or action.get("id", ""),
            "title": action.get("title", ""),
            "next_action": action.get("next_action", ""),
            "recommended_command": action.get("recommended_command", ""),
            "followup_command": action.get("followup_command", ""),
            "fallback_command": action.get("fallback_command", ""),
            "why": action.get("why", []),
        }
        if item_id:
            row["runbook_command"] = f"curator_workbench action=runbook item_id={item_id}"
        actions.append(row)

    compact = {
        "date": plan.get("date", ""),
        "commands": dict(plan.get("pipeline_commands") or {}),
        "pipeline_status": plan.get("pipeline_status") or {},
        "counts": {
            "pending_inbox": len(plan.get("pending_inbox") or []),
            "inbox_groups": len(plan.get("inbox_groups") or []),
            "pending_candidates": len(plan.get("candidate_cards") or []),
            "ready_candidates": len(plan.get("ready_candidate_cards") or []),
            "actions": len(plan.get("actions") or []),
        },
        "health": {
            "git": {
                "branch": git.get("branch", ""),
                "changed": git.get("changed", 0),
                "untracked": git.get("untracked", 0),
                "ahead": git.get("ahead", 0),
                "behind": git.get("behind", 0),
                "stashes": git.get("stashes", 0),
                "warnings": git.get("warnings", []),
            },
            "preflight": {
                "ok": preflight.get("ok") if preflight else None,
                "issues": preflight.get("issues", []) if preflight else [],
                "snapshot": preflight.get("snapshot", {}) if preflight else {},
            },
            "laptop": {
                "status": laptop.get("status", "unknown"),
                "available": laptop.get("available", False),
                "passed": laptop.get("passed", 0),
                "total": laptop.get("total", 0),
                "warnings": laptop.get("warnings", []),
                "failed_checks": failed_laptop_checks,
                "remediation": laptop_remediation_commands(
                    {
                        **dict(laptop),
                        "failed_checks": failed_laptop_checks,
                    }
                ),
            },
        },
        "actions": actions,
        "runbook": {
            "all": "curator_workbench action=runbook",
            "top": "curator_workbench action=runbook item_id=top",
        },
        "weight_recommendations": list(plan.get("weight_recommendations") or [])[:10],
        "weight_policy_draft": plan.get("weight_policy_draft") or {},
        "artifacts": {
            "curation_report": (plan.get("curation_report") or {}).get("path", ""),
            "daily_synthesis": (plan.get("daily_synthesis") or {}).get("path", ""),
            "transversal_synthesis": (plan.get("transversal_synthesis") or {}).get("path", ""),
        },
        "previews": {
            "curation": (plan.get("curation_report") or {}).get("preview", [])[:6],
            "daily_synthesis": (plan.get("daily_synthesis") or {}).get("preview", [])[:6],
            "transversal_synthesis": (plan.get("transversal_synthesis") or {}).get("preview", [])[:6],
        },
    }
    compact["priorities"] = morning_plan_priorities(compact)
    compact["summary"] = morning_plan_summary(compact)
    compact["risk"] = morning_plan_risk(compact)
    return compact


def morning_plan_summary(compact_plan: Mapping[str, Any]) -> str:
    """Build a one-line operational summary for the daily automation."""

    pipeline = compact_plan.get("pipeline_status") if isinstance(compact_plan.get("pipeline_status"), Mapping) else {}
    counts = compact_plan.get("counts") if isinstance(compact_plan.get("counts"), Mapping) else {}
    health = compact_plan.get("health") if isinstance(compact_plan.get("health"), Mapping) else {}
    laptop = health.get("laptop") if isinstance(health.get("laptop"), Mapping) else {}
    preflight = health.get("preflight") if isinstance(health.get("preflight"), Mapping) else {}
    status = str(pipeline.get("status") or "unknown")
    preflight_text = "ok" if preflight.get("ok") is True else "issues" if preflight.get("ok") is False else "not_run"
    return (
        f"status={status}; actions={counts.get('actions', 0)}; "
        f"preflight={preflight_text}; laptop={laptop.get('status', 'unknown')}"
    )


def morning_plan_risk(compact_plan: Mapping[str, Any]) -> str:
    """Return the main risk if Mauro does not touch anything today."""

    priorities = list(compact_plan.get("priorities") or [])
    pipeline = compact_plan.get("pipeline_status") if isinstance(compact_plan.get("pipeline_status"), Mapping) else {}
    issues = [str(item) for item in pipeline.get("issues") or [] if str(item).strip()]
    if priorities:
        top = priorities[0]
        return f"{top.get('title', 'Prioridad pendiente')}: {top.get('reason', '')}".strip()
    if issues:
        return issues[0]
    return "Sin riesgo operativo inmediato; mantener monitoreo diario."


def morning_plan_priorities(compact_plan: Mapping[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    """Derive a small ordered worklist from a compact morning plan."""

    priorities: list[dict[str, Any]] = []
    actions = list(compact_plan.get("actions") or [])
    health = compact_plan.get("health") if isinstance(compact_plan.get("health"), Mapping) else {}
    git = health.get("git") if isinstance(health.get("git"), Mapping) else {}
    preflight = health.get("preflight") if isinstance(health.get("preflight"), Mapping) else {}
    laptop = health.get("laptop") if isinstance(health.get("laptop"), Mapping) else {}
    weights = list(compact_plan.get("weight_recommendations") or [])

    if actions:
        top = actions[0]
        priorities.append(
            {
                "priority": "P1",
                "title": f"Curar cola de memoria: {top.get('title', top.get('kind', 'item'))}",
                "reason": f"Hay {len(actions)} accion(es) curatoriales pendientes.",
                "command": top.get("runbook_command") or "curator_workbench action=runbook item_id=top",
            }
        )
    if preflight and preflight.get("ok") is False:
        priorities.append(
            {
                "priority": f"P{len(priorities) + 1}",
                "title": "Resolver preflight local de memoria",
                "reason": "; ".join(str(item) for item in list(preflight.get("issues") or [])[:3]) or "preflight local con issues",
                "command": "python scripts\\daily_memory_report.py --preview --preflight --json --compact-json",
            }
        )
    laptop_status = str(laptop.get("status") or "")
    if laptop_status in {"degraded", "error", "unknown"}:
        failed = laptop.get("failed_checks") or []
        failed_names = ", ".join(str(item.get("name", "")) for item in failed if isinstance(item, Mapping))
        remediation = list(laptop.get("remediation") or [])
        command = "python ops\\remote\\kairos_remote.py doctor --node laptop --json"
        followup_command = ""
        manual_apply_command = ""
        for item in remediation:
            if not isinstance(item, Mapping):
                continue
            kind = str(item.get("kind") or "")
            if kind == "diagnose" and str(item.get("command") or ""):
                command = str(item.get("command"))
            elif kind == "preview" and str(item.get("command") or ""):
                followup_command = str(item.get("command"))
            elif kind == "manual_apply" and str(item.get("command") or ""):
                manual_apply_command = str(item.get("command"))
        priorities.append(
            {
                "priority": f"P{len(priorities) + 1}",
                "title": "Revisar health de laptop",
                "reason": failed_names or f"laptop status={laptop_status}",
                "command": command,
                "followup_command": followup_command,
                "manual_apply_command": manual_apply_command,
            }
        )
    if int(git.get("changed") or 0) > 0 or int(git.get("untracked") or 0) > 0:
        priorities.append(
            {
                "priority": f"P{len(priorities) + 1}",
                "title": "Revisar cambios locales antes de cerrar el tramo",
                "reason": f"changed={git.get('changed', 0)}, untracked={git.get('untracked', 0)}",
                "command": "git status --short --branch",
            }
        )
    if weights:
        priorities.append(
            {
                "priority": f"P{len(priorities) + 1}",
                "title": "Auditar pesos de retrieval antes de aprobar draft",
                "reason": f"{len(weights)} recomendacion(es) de peso requieren revision manual.",
                "command": "curator_workbench action=audit_weight_policy_suite",
            }
        )
    pipeline = compact_plan.get("pipeline_status") if isinstance(compact_plan.get("pipeline_status"), Mapping) else {}
    pipeline_issues = [str(item) for item in pipeline.get("issues") or []]
    missing_artifact = any(
        issue in {
            "no curation report found",
            "no daily synthesis found",
            "no transversal synthesis found",
            "transversal synthesis has no sessions",
        }
        for issue in pipeline_issues
    )
    if missing_artifact:
        commands = compact_plan.get("commands") if isinstance(compact_plan.get("commands"), Mapping) else {}
        priorities.append(
            {
                "priority": f"P{len(priorities) + 1}",
                "title": "Preparar capas de memoria antes del plan",
                "reason": "; ".join(pipeline_issues[:3]),
                "command": commands.get("prepare_layers")
                or "python scripts\\generate_session_summaries.py --embed --candidates --transversal --transversal-candidates --embed-transversal --embed-candidates --embed-inbox --daily-synthesis --curation-report --json",
            }
        )
    if not priorities:
        priorities.append(
            {
                "priority": "P1",
                "title": "Sin trabajo curatorial pendiente",
                "reason": "Pipeline sin acciones pendientes; mantener monitoreo diario.",
                "command": "python scripts\\daily_memory_report.py --preview --preflight --json --compact-json",
            }
        )

    for index, item in enumerate(priorities[:limit], 1):
        item["priority"] = f"P{index}"
    return priorities[:limit]


def render_morning_plan_json(plan: Mapping[str, Any], *, compact: bool = False) -> str:
    """Render a morning plan as stable JSON."""

    payload = compact_morning_plan(plan) if compact else plan
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_morning_plan(plan: Mapping[str, Any]) -> str:
    """Render a morning plan as Markdown."""

    lines: list[str] = [
        f"# Morning Memory Plan - {plan.get('date', '')}",
        "",
        "## Snapshot",
        "",
        f"- Pending inbox items: {len(plan.get('pending_inbox') or [])}",
        f"- Inbox groups: {len(plan.get('inbox_groups') or [])}",
        f"- Pending candidates: {len(plan.get('candidate_cards') or [])}",
        f"- Ready candidates: {len(plan.get('ready_candidate_cards') or [])}",
    ]
    curation = plan.get("curation_report") or {}
    synthesis = plan.get("daily_synthesis") or {}
    transversal = plan.get("transversal_synthesis") or {}
    if curation.get("path"):
        lines.append(f"- Latest curation report: `{curation.get('path')}`")
    decisions = plan.get("curation_decisions") or []
    if decisions:
        lines.append(f"- Curation decisions today: {len(decisions)}")
    relation_decisions = plan.get("relation_decisions") or []
    if relation_decisions:
        lines.append(f"- Relation decisions today: {len(relation_decisions)}")
    if synthesis.get("path"):
        lines.append(f"- Latest synthesis: `{synthesis.get('path')}`")
    if transversal.get("path"):
        lines.append(f"- Latest transversal synthesis: `{transversal.get('path')}`")
        channels = (transversal.get("metadata") or {}).get("channels") or {}
        if isinstance(channels, Mapping) and channels:
            channel_text = ", ".join(f"{name}: {count}" for name, count in sorted(channels.items()))
            lines.append(f"- Channels covered: {channel_text}")
    lines.append("")

    pipeline = plan.get("pipeline_status") or {}
    lines.append("## Pipeline Status")
    lines.append("")
    lines.append(f"- Status: `{pipeline.get('status', 'unknown')}`")
    lines.append(
        f"- Queue: inbox_groups={pipeline.get('inbox_groups', 0)}, "
        f"pending_candidates={pipeline.get('pending_candidates', 0)}, "
        f"ready_candidates={pipeline.get('ready_candidates', 0)}"
    )
    issues = list(pipeline.get("issues") or [])
    next_steps = list(pipeline.get("next_steps") or [])
    if issues:
        lines.append("- Issues:")
        lines.extend(f"  - {issue}" for issue in issues[:8])
    if next_steps:
        lines.append("- Next steps:")
        lines.extend(f"  - {step}" for step in next_steps[:8])
    lines.append("")

    commands = plan.get("pipeline_commands") or {}
    if commands:
        lines.append("## Operational Commands")
        lines.append("")
        prepare_layers = str(commands.get("prepare_layers") or "").strip()
        compact_report = str(commands.get("compact_report") or "").strip()
        runbook = str(commands.get("runbook") or "").strip()
        runbook_top = str(commands.get("runbook_top") or "").strip()
        if prepare_layers:
            lines.append(f"- Prepare memory layers: `{prepare_layers}`")
        if compact_report:
            lines.append(f"- Compact report: `{compact_report}`")
        if runbook:
            lines.append(f"- Curator runbook: `{runbook}`")
        if runbook_top:
            lines.append(f"- First curator item: `{runbook_top}`")
        lines.append("")

    health = plan.get("health") or {}
    git = health.get("git") or {}
    preflight = health.get("preflight") or {}
    laptop = health.get("laptop") or {}
    lines.append("## Health")
    lines.append("")
    if git.get("available"):
        lines.append(
            f"- Git: branch `{git.get('branch', '')}`, changed={git.get('changed', 0)}, "
            f"untracked={git.get('untracked', 0)}, ahead={git.get('ahead', 0)}, behind={git.get('behind', 0)}, "
            f"stashes={git.get('stashes', 0)}"
        )
    else:
        lines.append(f"- Git: unavailable ({'; '.join(git.get('warnings') or [])})")
    if preflight:
        status = "ok" if preflight.get("ok") else "issues"
        issues = preflight.get("issues") or []
        suffix = f" - {', '.join(str(item) for item in issues[:3])}" if issues else ""
        lines.append(f"- Memory preflight: {status}{suffix}")
    else:
        lines.append("- Memory preflight: not run")
    lines.append(f"- Laptop: {laptop.get('status', 'unknown')}")
    remediation = laptop_remediation_commands(laptop) if isinstance(laptop, Mapping) else []
    if remediation:
        lines.append("")
        lines.append("### Laptop Remediation")
        for item in remediation:
            label = str(item.get("label") or item.get("kind") or "command")
            command = str(item.get("command") or "").strip()
            if command:
                lines.append(f"- {label}: `{command}`")
    warnings = list(git.get("warnings") or []) + list(laptop.get("warnings") or [])
    if preflight.get("issues"):
        warnings.extend(str(issue) for issue in preflight.get("issues", []))
    if warnings:
        lines.append("")
        lines.append("### Warnings")
        lines.extend(f"- {warning}" for warning in warnings[:12])
    lines.append("")

    actions = list(plan.get("actions") or [])
    lines.append("## Today's Work")
    lines.append("")
    if actions:
        lines.append("- Guided runbook: `curator_workbench action=runbook`")
        lines.append("- Start here: `curator_workbench action=runbook item_id=top`")
        lines.append("")
        for idx, action in enumerate(actions[:12], 1):
            lines.append(f"{idx}. **P{action.get('priority', 0)} {action.get('kind', '')}** - {action.get('title', '')}")
            detail = str(action.get("detail") or "").strip()
            artifact = str(action.get("artifact") or "").strip()
            recommended_command = str(action.get("recommended_command") or "").strip()
            followup_command = str(action.get("followup_command") or "").strip()
            fallback_command = str(action.get("fallback_command") or "").strip()
            item_id = _queue_item_id_for_command(action)
            if detail:
                lines.append(f"   - Detail: {detail}")
            if item_id:
                lines.append(f"   - Runbook: `curator_workbench action=runbook item_id={item_id}`")
            if recommended_command:
                lines.append(f"   - Command: `{recommended_command}`")
            if followup_command:
                lines.append(f"   - Follow-up: `{followup_command}`")
            if fallback_command:
                lines.append(f"   - Fallback: `{fallback_command}`")
            if artifact:
                lines.append(f"   - Artifact: `{artifact}`")
    else:
        lines.append("- No pending memory work found.")
    lines.append("")

    if curation.get("preview"):
        lines.append("## Curation Notes")
        lines.append("")
        lines.extend(f"- {line}" for line in curation["preview"])
        lines.append("")

    if decisions:
        lines.append("## Curation Decisions")
        lines.append("")
        for decision in decisions[:10]:
            lines.append(
                f"- {decision.get('action', '')} {decision.get('kind', '')} "
                f"`{decision.get('group_id') or decision.get('candidate_id') or ''}` "
                f"reinforced={decision.get('reinforcement_count', 1)}"
            )
        lines.append("")

    relation_decisions = plan.get("relation_decisions") or []
    if relation_decisions:
        lines.append("## Relation Decisions")
        lines.append("")
        for relation in relation_decisions[:10]:
            lines.append(
                f"- `{relation.get('source_id', '')}` "
                f"-[{relation.get('relation_type', '')}]-> "
                f"`{relation.get('target_id', '')}` "
                f"weight={relation.get('weight', '')} action={relation.get('action', '')}"
            )
            evidence = str(relation.get("evidence") or "").strip()
            if evidence:
                lines.append(f"  - Evidence: {evidence}")
            command = str(relation.get("explain_command") or "").strip()
            if command:
                lines.append(f"  - Explain: `{command}`")
        lines.append("")

    feedback = plan.get("curation_feedback") or []
    if feedback:
        lines.append("## Curation Feedback")
        lines.append("")
        for item in feedback[:10]:
            actions = item.get("actions") if isinstance(item.get("actions"), Mapping) else {}
            top_actions = ", ".join(f"{key}:{value}" for key, value in sorted(actions.items())[:4])
            lines.append(
                f"- `{item.get('source', '')}` total={item.get('total', 0)} "
                f"positive={item.get('positive_rate', 0)} "
                f"negative={item.get('negative_rate', 0)} "
                f"blocked={item.get('blocked_rate', 0)} "
                f"suggestion={item.get('suggested_adjustment', 'hold')}"
            )
            if top_actions:
                lines.append(f"  - Actions: {top_actions}")
        lines.append("")

    weight_recommendations = plan.get("weight_recommendations") or []
    if weight_recommendations:
        lines.append("## Retrieval Weight Recommendations")
        lines.append("")
        lines.append("- Audit first: `curator_workbench action=audit_weight_policy_suite`")
        lines.append("- Draft after review: `curator_workbench action=write_weight_policy_draft`")
        for item in weight_recommendations[:10]:
            lines.append(
                f"- `{item.get('layer', '')}` from `{item.get('source', '')}`: "
                f"{item.get('current_weight', '')} -> {item.get('proposed_weight', '')} "
                f"delta={item.get('delta', '')} samples={item.get('sample_size', 0)} "
                f"policy={item.get('apply_policy', '')}"
            )
            rationale = str(item.get("rationale") or "").strip()
            if rationale:
                lines.append(f"  - Rationale: {rationale}")
        lines.append("")

    weight_policy_draft = plan.get("weight_policy_draft") or {}
    changes = weight_policy_draft.get("changes") if isinstance(weight_policy_draft, Mapping) else []
    if changes:
        lines.append("## Retrieval Weight Policy Draft")
        lines.append("")
        lines.append(f"- Version: `{weight_policy_draft.get('version', '')}`")
        lines.append(f"- Status: `{weight_policy_draft.get('status', '')}`")
        lines.append(f"- Apply policy: `{weight_policy_draft.get('apply_policy', '')}`")
        lines.append(f"- Draft path: `{weight_policy_draft.get('path', '')}`")
        for change in list(changes)[:10]:
            lines.append(
                f"- `{change.get('layer', '')}`: "
                f"{change.get('current_weight', '')} -> {change.get('proposed_weight', '')} "
                f"delta={change.get('delta', '')} samples={change.get('sample_size', 0)}"
            )
        lines.append("")

    if synthesis.get("preview"):
        lines.append("## Recent Synthesis")
        lines.append("")
        lines.extend(f"- {line}" for line in synthesis["preview"])
        lines.append("")

    if transversal.get("preview"):
        lines.append("## Transversal Signals")
        lines.append("")
        lines.extend(f"- {line}" for line in transversal["preview"])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_morning_plan(
    root: str | Path | None = None,
    target_date: date | None = None,
    include_preflight: bool = False,
    laptop_status_json: str | Path | None = None,
    laptop_status_command: str | None = None,
    laptop_status_timeout: int = 45,
) -> Path:
    """Build, render, and write the morning plan artifact."""

    plan = build_morning_plan(
        root=root,
        target_date=target_date,
        include_preflight=include_preflight,
        laptop_status_json=laptop_status_json,
        laptop_status_command=laptop_status_command,
        laptop_status_timeout=laptop_status_timeout,
    )
    path = morning_plan_path(str(plan["date"]), root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_morning_plan(plan), encoding="utf-8")
    return path
