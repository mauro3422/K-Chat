"""Artifacts produced by the nightly curation pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def curation_report_path(timestamp: str, root: str | Path | None = None) -> Path:
    """Return the daily Markdown path for a curator run report."""

    date = timestamp[:10] if timestamp else datetime.now().date().isoformat()
    year, month, day = date.split("-")
    base = Path(root) if root is not None else _project_root()
    return base / "memory" / "events" / "curation" / year / month / f"{day}.md"


def curation_decision_path(timestamp: str, root: str | Path | None = None) -> Path:
    """Return the daily JSONL path for curator decisions."""

    date = timestamp[:10] if timestamp else datetime.now().date().isoformat()
    year, month, day = date.split("-")
    base = Path(root) if root is not None else _project_root()
    return base / "memory" / "events" / "curation" / year / month / f"{day}.decisions.jsonl"


def tracer_candidate_path(timestamp: str, root: str | Path | None = None) -> Path:
    """Return the daily JSONL path for tracer pattern candidates."""

    date = timestamp[:10] if timestamp else datetime.now().date().isoformat()
    year, month, day = date.split("-")
    base = Path(root) if root is not None else _project_root()
    return base / "memory" / "candidates" / year / month / f"{day}.tracer.jsonl"


def write_curation_report(
    lines: list[str],
    metadata: Mapping[str, Any],
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> Path:
    """Write a curator run report artifact."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    path = curation_report_path(ts, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines)
    meta = json.dumps(dict(metadata), ensure_ascii=False, sort_keys=True)
    path.write_text(f"{body}\n\n<!-- metadata: {meta} -->\n", encoding="utf-8")
    return path


def append_curation_decision(
    event: Mapping[str, Any],
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Append a curator decision event and return the persisted payload."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    path = curation_decision_path(ts, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": ts, **dict(event)}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    payload["artifact"] = str(path)
    return payload


def load_curation_decisions(
    root: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Load recent curator decision JSONL events."""

    base = Path(root) if root is not None else _project_root()
    curation_root = base / "memory" / "events" / "curation"
    if not curation_root.exists():
        return []

    decisions: list[dict[str, Any]] = []
    for path in sorted(curation_root.rglob("*.decisions.jsonl"), reverse=True):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    payload["_artifact"] = str(path)
                    decisions.append(payload)
                    if len(decisions) >= limit:
                        return decisions
    return decisions


async def materialize_relation_hints(
    entity_repo: Any,
    root: str | Path | None = None,
    limit: int = 100,
    timestamp: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Persist or preview relation_hints from curation decisions."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    decisions = load_curation_decisions(root=root, limit=limit)
    seen: set[tuple[str, str, str]] = set()
    materialized: list[dict[str, Any]] = []
    skipped = 0
    for decision in decisions:
        hints = decision.get("relation_hints") or []
        if not isinstance(hints, list):
            continue
        for hint in hints:
            if not isinstance(hint, Mapping):
                skipped += 1
                continue
            source_id = str(hint.get("source_id") or "").strip()
            target_id = str(hint.get("target_id") or "").strip()
            relation_type = str(hint.get("relation_type") or "").strip()
            if not source_id or not target_id or not relation_type:
                skipped += 1
                continue
            identity = (source_id, target_id, relation_type)
            if identity in seen:
                skipped += 1
                continue
            seen.add(identity)
            weight = float(hint.get("weight") or decision.get("reinforcement_count") or 1.0)
            curated_relation_id = ""
            if not dry_run:
                await entity_repo.upsert_relation(
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation_type,
                    weight=weight,
                    timestamp=ts,
                )
                if hasattr(entity_repo, "upsert_curated_relation"):
                    curated_relation_id = await entity_repo.upsert_curated_relation(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type=relation_type,
                        weight=weight,
                        candidate_id=str(decision.get("candidate_id") or decision.get("group_id") or ""),
                        provenance={
                            "source": "curation_decision_relation_hint",
                            "decision_action": decision.get("action", ""),
                            "decision_kind": decision.get("kind", ""),
                            "decision_artifact": decision.get("_artifact") or decision.get("artifact", ""),
                            "decision_created_at": decision.get("created_at", ""),
                            "relation_provenance": hint.get("provenance", ""),
                        },
                        evidence=str(decision.get("value") or decision.get("query") or decision.get("reason") or ""),
                        metadata={
                            "decision": {
                                key: value
                                for key, value in decision.items()
                                if key not in {"relation_hints"}
                            },
                            "relation_hint": dict(hint),
                        },
                        timestamp=ts,
                    )
            materialized.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type,
                    "weight": weight,
                    "curated_relation_id": curated_relation_id,
                    "candidate_id": str(decision.get("candidate_id") or decision.get("group_id") or ""),
                    "evidence": str(decision.get("value") or decision.get("query") or decision.get("reason") or ""),
                    "dry_run": dry_run,
                }
            )
    return {
        "dry_run": dry_run,
        "materialized": 0 if dry_run else len(materialized),
        "previewed": len(materialized) if dry_run else 0,
        "skipped": skipped,
        "relations": materialized,
    }


async def upsert_curator_relation(
    entity_repo: Any,
    *,
    source_id: str,
    target_id: str,
    relation_type: str,
    weight: float = 1.0,
    evidence: str = "",
    reason: str = "",
    candidate_id: str = "",
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Persist a curator-authored relation and log the decision."""

    source = str(source_id or "").strip()
    target = str(target_id or "").strip()
    rel_type = str(relation_type or "").strip().upper()
    if not source:
        raise ValueError("source_id cannot be empty")
    if not target:
        raise ValueError("target_id cannot be empty")
    if not rel_type:
        raise ValueError("relation_type cannot be empty")

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    rel_weight = float(weight)
    await entity_repo.upsert_relation(
        source_id=source,
        target_id=target,
        relation_type=rel_type,
        weight=rel_weight,
        timestamp=ts,
    )
    curated_relation_id = ""
    if hasattr(entity_repo, "upsert_curated_relation"):
        curated_relation_id = await entity_repo.upsert_curated_relation(
            source_id=source,
            target_id=target,
            relation_type=rel_type,
            weight=rel_weight,
            candidate_id=str(candidate_id or ""),
            provenance={
                "source": "curator_relation_upsert",
                "reason": reason,
            },
            evidence=evidence,
            metadata={
                "reason": reason,
                "manual": True,
            },
            timestamp=ts,
        )

    decision = append_curation_decision(
        {
            "kind": "memory_relation",
            "action": "upsert_relation",
            "source_id": source,
            "target_id": target,
            "relation_type": rel_type,
            "weight": rel_weight,
            "evidence": evidence,
            "reason": reason,
            "candidate_id": str(candidate_id or ""),
            "curated_relation_id": curated_relation_id,
        },
        root=root,
        timestamp=ts,
    )
    return {
        "source_id": source,
        "target_id": target,
        "relation_type": rel_type,
        "weight": rel_weight,
        "evidence": evidence,
        "reason": reason,
        "candidate_id": str(candidate_id or ""),
        "curated_relation_id": curated_relation_id,
        "decision_event": decision,
    }


def _candidate_id(pattern: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(pattern), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def tracer_candidates_from_patterns(patterns: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert tracer patterns into reviewable memory candidates."""

    candidates: list[dict[str, Any]] = []
    for pattern in patterns:
        pattern_type = str(pattern.get("type") or "")
        if pattern_type == "recall_link_candidate":
            continue
        if pattern_type == "repeated_query" and int(pattern.get("times") or 0) < 5:
            continue
        if pattern_type == "entity_cooccurrence" and float(pattern.get("weight") or 0) < 5:
            continue
        candidate = {
            "type": "tracer_pattern_candidate",
            "candidate_id": _candidate_id(pattern),
            "status": "pending",
            "source": "tracer",
            "pattern_type": pattern_type,
            "confidence": float(pattern.get("avg_score") or pattern.get("weight") or 0.5),
            "pattern": dict(pattern),
        }
        if pattern_type == "debug_session":
            candidate["urgency"] = "high"
        candidates.append(candidate)
    return candidates


def write_tracer_candidates(
    candidates: list[Mapping[str, Any]],
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> Path | None:
    """Write tracer candidates for curator review."""

    if not candidates:
        return None

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    path = tracer_candidate_path(ts, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            payload = {"created_at": ts, **dict(candidate)}
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path
