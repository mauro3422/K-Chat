from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "curator_quality_probe.py"
    spec = importlib.util.spec_from_file_location("curator_quality_probe_test", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_results_reports_quality_signals() -> None:
    module = load_module()
    summary = module.summarize_results(
        [
            {
                "ok": True,
                "elapsed_ms": 100,
                "no_new_info": False,
                "malformed": False,
                "parsed_entries": [{"key": "bug:a"}, {"key": "user:b"}],
                "kept_entries": [{"key": "bug:a"}],
                "filter_stats": {"trivial": 1, "duplicates": 0},
            },
            {
                "ok": False,
                "elapsed_ms": 50,
                "parsed_entries": [],
                "kept_entries": [],
                "filter_stats": {"trivial": 0, "duplicates": 0},
            },
        ]
    )

    assert summary["calls"] == 2
    assert summary["successful"] == 1
    assert summary["failed"] == 1
    assert summary["parsed_entries"] == 2
    assert summary["kept_entries"] == 1
    assert summary["trivial_removed"] == 1
    assert summary["latency_mean_ms"] == 100


def test_compare_runs_requires_same_bundle_and_compares_keys() -> None:
    module = load_module()
    left = {
        "bundle_id": "same",
        "node": "pc",
        "summary": {"successful": 1},
        "calls": [
            {
                "case_id": "one",
                "repeat": 0,
                "kept_entries": [{"key": "bug:a"}, {"key": "decision:b"}],
            }
        ],
    }
    right = {
        "bundle_id": "same",
        "node": "laptop",
        "summary": {"successful": 1},
        "calls": [
            {
                "case_id": "one",
                "repeat": 0,
                "kept_entries": [{"key": "bug:a"}, {"key": "user:c"}],
            }
        ],
    }

    comparison = module.compare_runs(left, right)

    assert comparison["matched_calls"] == 1
    assert comparison["key_jaccard_mean"] == 0.3333
