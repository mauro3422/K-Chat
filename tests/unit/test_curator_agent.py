import json

import pytest

from src.memory.curator.agent import CuratorAgent
from src.memory.curator.benchmark import benchmark_candidate_records, run_ab_benchmark


class FakeScorer:
    def __init__(self):
        self._weights = {"candidate_base": 0.6}

    @property
    def weights(self):
        return dict(self._weights)

    def set_weight(self, key, value):
        self._weights[key] = value


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_curator_agent_reviews_session_and_adjusts_weights(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    _write_jsonl(
        candidates,
        [{"candidate_id": "c1", "session_id": "s1", "source": "session_summary"}],
    )
    persisted = []
    scorer = FakeScorer()
    agent = CuratorAgent(
        scorer,
        candidates,
        root=tmp_path,
        persist_weights_fn=lambda weights: persisted.append(dict(weights)),
    )

    assert agent.review_session("s1", "promote", "useful") == 1
    weights = agent.commit_adjustments()

    assert weights["candidate_base"] > 0.6
    assert persisted == [weights]


def test_curator_agent_requires_injected_pipeline(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    _write_jsonl(candidates, [])
    agent = CuratorAgent(FakeScorer(), candidates, root=tmp_path)

    with pytest.raises(RuntimeError, match="not injected"):
        agent.re_run_pipeline()


def test_benchmark_candidate_records_computes_precision_recall_and_f1():
    candidates = [
        {"candidate_id": "c1", "confidence": 0.9},
        {"candidate_id": "c2", "confidence": 0.8},
        {"candidate_id": "c3", "confidence": 0.2},
    ]
    decisions = [
        {"candidate_id": "c1", "action": "promote"},
        {"candidate_id": "c2", "action": "reject"},
        {"candidate_id": "c3", "action": "promote"},
    ]

    result = benchmark_candidate_records(candidates, decisions, confidence_threshold=0.75)

    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5


def test_ab_benchmark_reports_metric_delta(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    treatment = tmp_path / "treatment.jsonl"
    decisions = [
        {"candidate_id": "c1", "action": "promote"},
        {"candidate_id": "c2", "action": "reject"},
    ]
    _write_jsonl(
        baseline,
        [
            {"candidate_id": "c1", "confidence": 0.6},
            {"candidate_id": "c2", "confidence": 0.9},
        ],
    )
    _write_jsonl(
        treatment,
        [
            {"candidate_id": "c1", "confidence": 0.9},
            {"candidate_id": "c2", "confidence": 0.2},
        ],
    )

    result = run_ab_benchmark(baseline, treatment, decisions)

    assert result["baseline"]["f1"] == 0.0
    assert result["treatment"]["f1"] == 1.0
    assert result["delta"]["f1"] == 1.0
