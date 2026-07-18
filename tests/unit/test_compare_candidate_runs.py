from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "compare_candidate_runs.py"
    spec = importlib.util.spec_from_file_location("compare_candidate_runs_test", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_compare_candidate_runs_reports_deltas(tmp_path: Path) -> None:
    module = load_module()
    baseline = tmp_path / "baseline.jsonl"
    treatment = tmp_path / "treatment.jsonl"
    write_jsonl(
        baseline,
        [
            {"confidence": 0.2, "promotion_decision": "hold"},
            {"confidence": 0.6, "promotion_decision": "review"},
        ],
    )
    write_jsonl(
        treatment,
        [
            {"confidence": 0.1, "promotion_decision": "hold"},
            {"confidence": 0.9, "promotion_decision": "auto_promote"},
        ],
    )

    comparison = module.compare_candidate_runs(baseline, treatment)

    assert comparison["baseline"]["n"] == 2
    assert comparison["treatment"]["n"] == 2
    assert comparison["std_delta"] > 0
    assert comparison["non_hold_delta"] == 0


def test_format_comparison_includes_malformed_counts(tmp_path: Path) -> None:
    module = load_module()
    baseline = tmp_path / "baseline.jsonl"
    treatment = tmp_path / "treatment.jsonl"
    baseline.write_text('{"confidence": 0.4, "status": "hold"}\nnot-json\n', encoding="utf-8")
    treatment.write_text('{"score": 0.7, "status": "ready"}\n', encoding="utf-8")

    report = module.format_comparison(
        module.compare_candidate_runs(baseline, treatment),
        baseline_name=baseline.name,
        treatment_name=treatment.name,
    )

    assert "count: 1 -> 1" in report
    assert "hold: 1 -> 0" in report
    assert "ready: 0 -> 1" in report
    assert "malformed: 1 -> 0" in report
