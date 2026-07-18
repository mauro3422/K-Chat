#!/usr/bin/env python3
"""Compare candidate JSONL run statistics without mutating artifacts."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def analyze_candidate_run(path: Path) -> dict[str, Any]:
    """Return count, confidence, and decision stats for a candidate JSONL artifact."""
    if not path.exists():
        return {}

    confidences: list[float] = []
    decisions: dict[str, int] = {}
    malformed = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue

            confidence = data.get("confidence", data.get("score", 0.0))
            try:
                confidences.append(float(confidence))
            except (TypeError, ValueError):
                confidences.append(0.0)

            decision = str(data.get("promotion_decision", data.get("status", "hold")))
            decisions[decision] = decisions.get(decision, 0) + 1

    if not confidences:
        return {"malformed": malformed} if malformed else {}

    count = len(confidences)
    mean = sum(confidences) / count
    variance = sum((confidence - mean) ** 2 for confidence in confidences) / max(count - 1, 1)

    return {
        "n": count,
        "mean": mean,
        "std": math.sqrt(variance),
        "min": min(confidences),
        "max": max(confidences),
        "decisions": decisions,
        "malformed": malformed,
    }


def compare_candidate_runs(baseline: Path, treatment: Path) -> dict[str, Any]:
    """Compare two candidate runs and return structured summary metrics."""
    baseline_stats = analyze_candidate_run(baseline)
    treatment_stats = analyze_candidate_run(treatment)
    if not baseline_stats or "n" not in baseline_stats:
        raise ValueError(f"Baseline path empty, missing, or malformed: {baseline}")
    if not treatment_stats or "n" not in treatment_stats:
        raise ValueError(f"Treatment path empty, missing, or malformed: {treatment}")

    baseline_n = int(baseline_stats["n"])
    treatment_n = int(treatment_stats["n"])
    baseline_decisions = dict(baseline_stats["decisions"])
    treatment_decisions = dict(treatment_stats["decisions"])
    baseline_non_hold = baseline_n - int(baseline_decisions.get("hold", 0))
    treatment_non_hold = treatment_n - int(treatment_decisions.get("hold", 0))

    return {
        "baseline": baseline_stats,
        "treatment": treatment_stats,
        "std_delta": float(treatment_stats["std"]) - float(baseline_stats["std"]),
        "mean_delta": float(treatment_stats["mean"]) - float(baseline_stats["mean"]),
        "non_hold_delta": treatment_non_hold - baseline_non_hold,
    }


def format_comparison(comparison: dict[str, Any], *, baseline_name: str, treatment_name: str) -> str:
    """Format comparison metrics as a compact terminal report."""
    baseline = comparison["baseline"]
    treatment = comparison["treatment"]
    decisions = sorted(set(baseline["decisions"]) | set(treatment["decisions"]))
    lines = [
        f"Candidate run comparison: {baseline_name} vs {treatment_name}",
        f"count: {baseline['n']} -> {treatment['n']}",
        f"mean_confidence: {baseline['mean']:.4f} -> {treatment['mean']:.4f}",
        f"confidence_stddev: {baseline['std']:.4f} -> {treatment['std']:.4f}",
        f"min_confidence: {baseline['min']:.4f} -> {treatment['min']:.4f}",
        f"max_confidence: {baseline['max']:.4f} -> {treatment['max']:.4f}",
        f"std_delta: {comparison['std_delta']:.4f}",
        f"mean_delta: {comparison['mean_delta']:.4f}",
        f"non_hold_delta: {comparison['non_hold_delta']}",
        "decisions:",
    ]
    for decision in decisions:
        lines.append(
            f"  {decision}: "
            f"{baseline['decisions'].get(decision, 0)} -> {treatment['decisions'].get(decision, 0)}"
        )
    if baseline.get("malformed") or treatment.get("malformed"):
        lines.append(f"malformed: {baseline.get('malformed', 0)} -> {treatment.get('malformed', 0)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare candidate JSONL run statistics.")
    parser.add_argument("baseline", type=Path, help="Baseline candidate JSONL artifact.")
    parser.add_argument("treatment", type=Path, help="Treatment candidate JSONL artifact.")
    args = parser.parse_args()

    try:
        comparison = compare_candidate_runs(args.baseline, args.treatment)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    print(
        format_comparison(
            comparison,
            baseline_name=args.baseline.name,
            treatment_name=args.treatment.name,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
