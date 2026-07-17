from __future__ import annotations

from typing import Any, Mapping

from src.memory.health_contract import normalize_health_status


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

    preflight_status = normalize_health_status(
        preflight.get("status"),
        legacy_ok=preflight.get("ok"),
    )
    if preflight and preflight_status != "ok":
        issues.append(f"memory preflight {preflight_status}")
    if laptop.get("status") in {"not_configured", "error", "unknown", "degraded"}:
        issues.append(f"laptop health {laptop.get('status', 'unknown')}")

    if not next_steps:
        next_steps.append("no memory curation actions pending")

    blocking = [
        issue for issue in issues
        if "memory preflight error" in issue
        or "branch behind" in issue
        or "laptop health error" in issue
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
