from __future__ import annotations

import asyncio
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
    assert comparison["key_token_similarity_mean"] == 0.5


def test_compare_runs_normalizes_key_separators() -> None:
    module = load_module()
    left = {
        "bundle_id": "same",
        "node": "pc",
        "calls": [{"case_id": "one", "repeat": 0, "kept_entries": [{"key": "proyecto:db_schemas"}]}],
    }
    right = {
        "bundle_id": "same",
        "node": "laptop",
        "calls": [{"case_id": "one", "repeat": 0, "kept_entries": [{"key": "proyecto:db-schemas"}]}],
    }

    comparison = module.compare_runs(left, right)

    assert comparison["key_jaccard_mean"] == 0.0
    assert comparison["key_token_similarity_mean"] == 1.0


def test_repeat_consistency_compares_repeated_cases() -> None:
    module = load_module()
    calls = [
        {"case_id": "one", "repeat": 0, "kept_entries": [{"key": "proyecto:db_schemas"}]},
        {"case_id": "one", "repeat": 1, "kept_entries": [{"key": "proyecto:db-schemas"}]},
        {"case_id": "two", "repeat": 0, "kept_entries": [{"key": "bug:a"}]},
        {"case_id": "two", "repeat": 1, "kept_entries": []},
    ]

    consistency = module.repeat_consistency(calls)

    assert consistency["repeat_pairs"] == 2
    assert consistency["key_token_similarity_mean"] == 0.5


def test_strict_prompt_variant_adds_canonical_contract() -> None:
    module = load_module()

    prompt = module.system_prompt_variant("base", "strict")

    assert prompt.startswith("base")
    assert "at most 4 items" in prompt
    assert "lowercase kebab-case" in prompt
    assert "exactly NO_NEW_INFO" in prompt


def test_strict_prompt_variant_does_not_duplicate_existing_contract() -> None:
    module = load_module()
    prompt = module.system_prompt_variant(
        "base\n\nSTRICT OUTPUT CONTRACT:\n- existing",
        "strict",
    )

    assert prompt.count("STRICT OUTPUT CONTRACT:") == 1


def test_contextual_run_injects_provisional_entries(monkeypatch) -> None:
    module = load_module()
    system_prompts: list[str] = []

    async def fake_call(system: str, _user: str, _model: str, _temperature: float):
        system_prompts.append(system)
        entries = []
        if len(system_prompts) == 1:
            entries = [{"key": "decision:first", "value": "2026-07-10 12:00 | First fact."}]
        return {
            "ok": True,
            "elapsed_ms": 1,
            "parsed_entries": entries,
            "kept_entries": entries,
            "filter_stats": {"trivial": 0, "invalid_category": 0, "duplicates": 0},
        }

    monkeypatch.setattr(module, "_run_call", fake_call)
    bundle = {
        "bundle_id": "bundle",
        "current_date": "2026-07-10 12:00",
        "curator_prompt": "CURATE",
        "system_prompt": "BASE",
        "cases": [
            {"case_id": "one", "prompt": "one", "relevant_context": "known one"},
            {"case_id": "two", "prompt": "two", "relevant_context": "known two"},
        ],
    }

    asyncio.run(
        module.run_bundle(
            bundle,
            model="model",
            repeats=1,
            node="node",
            prompt_variant="contextual",
        )
    )

    assert "known one" in system_prompts[0]
    assert "decision:first" not in system_prompts[0]
    assert "known two" in system_prompts[1]
    assert "decision:first" in system_prompts[1]
