"""A/B metrics for memory-candidate ranking against curator decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def load_candidate_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _ground_truth(decisions: Iterable[Mapping[str, Any]]) -> dict[str, bool]:
    labels: dict[str, bool] = {}
    for decision in decisions:
        candidate_id = str(decision.get("candidate_id") or "").strip()
        action = str(decision.get("action") or decision.get("decision") or "").strip()
        if not candidate_id:
            continue
        if action in {"promote", "promote_ready"}:
            labels[candidate_id] = True
        elif action == "reject":
            labels[candidate_id] = False
    return labels


def _predicted_positive(candidate: Mapping[str, Any], threshold: float) -> bool:
    decision = str(candidate.get("promotion_decision") or "").strip()
    if decision:
        return decision in {"review", "auto_promote", "promote", "promote_ready"}
    return float(candidate.get("confidence") or 0.0) >= threshold


def benchmark_candidate_records(
    candidates: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    *,
    confidence_threshold: float = 0.75,
) -> dict[str, float | int]:
    truth = _ground_truth(decisions)
    tp = fp = fn = tn = 0
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if candidate_id not in truth:
            continue
        predicted = _predicted_positive(candidate, confidence_threshold)
        actual = truth[candidate_id]
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "evaluated": tp + fp + fn + tn,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def run_ab_benchmark(
    baseline_path: str | Path,
    treatment_path: str | Path,
    decisions: Iterable[Mapping[str, Any]],
    *,
    confidence_threshold: float = 0.75,
) -> dict[str, Any]:
    decision_rows = [dict(item) for item in decisions]
    baseline = benchmark_candidate_records(
        load_candidate_jsonl(baseline_path),
        decision_rows,
        confidence_threshold=confidence_threshold,
    )
    treatment = benchmark_candidate_records(
        load_candidate_jsonl(treatment_path),
        decision_rows,
        confidence_threshold=confidence_threshold,
    )
    ready = int(baseline["evaluated"]) > 0 and int(treatment["evaluated"]) > 0
    return {
        "ready": ready,
        "blocked_reason": "" if ready else "no_matching_human_decisions",
        "baseline": baseline,
        "treatment": treatment,
        "delta": {
            metric: round(float(treatment[metric]) - float(baseline[metric]), 4)
            for metric in ("precision", "recall", "f1")
        },
    }
