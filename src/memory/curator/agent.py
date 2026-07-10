"""Feedback-driven curator agent composed from existing memory primitives."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from src.memory.curator.benchmark import load_candidate_jsonl, run_ab_benchmark
from src.memory.curator.curation_events import (
    append_curation_decision,
    load_curation_decisions,
)


class CandidateScorerProtocol(Protocol):
    @property
    def weights(self) -> dict[str, float]: ...

    def set_weight(self, key: str, value: float) -> None: ...


class CuratorAgent:
    """Review candidates, tune injected scoring weights, and compare runs."""

    def __init__(
        self,
        scorer: CandidateScorerProtocol,
        candidate_path: str | Path,
        *,
        root: str | Path | None = None,
        persist_weights_fn: Callable[[Mapping[str, float]], None] | None = None,
        rerun_pipeline_fn: Callable[[], Any] | None = None,
    ) -> None:
        self._scorer = scorer
        self._candidate_path = Path(candidate_path)
        self._root = root
        self._persist_weights_fn = persist_weights_fn
        self._rerun_pipeline_fn = rerun_pipeline_fn

    def review_candidates(self, path: str | Path | None = None) -> list[dict[str, Any]]:
        return load_candidate_jsonl(path or self._candidate_path)

    def review_session(self, session_id: str, decision: str, notes: str = "") -> int:
        if decision not in {"promote", "reject", "defer"}:
            raise ValueError("decision must be promote, reject, or defer")
        matches = [
            candidate
            for candidate in self.review_candidates()
            if str(candidate.get("session_id") or "") == session_id
        ]
        for candidate in matches:
            append_curation_decision(
                {
                    "kind": "memory_candidate",
                    "source": candidate.get("source", "session_summary"),
                    "session_id": session_id,
                    "candidate_id": candidate.get("candidate_id", ""),
                    "action": decision,
                    "notes": notes,
                },
                root=self._root,
            )
        return len(matches)

    def commit_adjustments(self, *, step: float = 0.02) -> dict[str, float]:
        decisions = load_curation_decisions(root=self._root, limit=1000)
        positive = sum(
            1 for item in decisions if str(item.get("action") or "") in {"promote", "promote_ready"}
        )
        negative = sum(1 for item in decisions if str(item.get("action") or "") == "reject")
        weights = self._scorer.weights
        if positive + negative:
            direction = (positive - negative) / (positive + negative)
            current = float(weights.get("candidate_base", 0.6))
            adjusted = min(0.9, max(0.1, current + step * direction))
            self._scorer.set_weight("candidate_base", adjusted)
            weights = self._scorer.weights
        if self._persist_weights_fn is not None:
            self._persist_weights_fn(weights)
        return weights

    def re_run_pipeline(self) -> Any:
        if self._rerun_pipeline_fn is None:
            raise RuntimeError("rerun_pipeline_fn was not injected")
        return self._rerun_pipeline_fn()

    def run_benchmark(
        self,
        baseline_candidates: str | Path,
        tuned_candidates: str | Path,
        *,
        confidence_threshold: float = 0.75,
    ) -> dict[str, Any]:
        decisions = load_curation_decisions(root=self._root, limit=1000)
        return run_ab_benchmark(
            baseline_candidates,
            tuned_candidates,
            decisions,
            confidence_threshold=confidence_threshold,
        )
