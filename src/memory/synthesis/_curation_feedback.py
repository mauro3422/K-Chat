from __future__ import annotations

from typing import Any, Mapping


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
