"""Cross-partition lifecycle and deduplication for curator candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.memory.curator.recall_review import load_candidates, write_candidates


_DECISION_FIELDS = (
    "status",
    "promotion_decision",
    "promotion_gate",
    "decision",
    "curation_decision",
    "reviewed_at",
    "reviewer",
)


def discover_candidate_artifacts(root: str | Path) -> list[Path]:
    """Return candidate artifacts newest-first, including the review queue."""

    base = Path(root) / "memory"
    if not base.exists():
        return []
    paths = list(base.glob("*/*/*/candidates/*.jsonl"))
    review_queue = base / "curator-review-queue.jsonl"
    if review_queue.exists():
        paths.append(review_queue)
    return sorted(paths, reverse=True)


def candidate_has_decision(candidate: Mapping[str, Any]) -> bool:
    status = str(candidate.get("status") or "pending").strip()
    return status != "pending" or bool(
        candidate.get("decision") or candidate.get("curation_decision")
    )


def _age_days(first_seen: str, observed_at: str) -> int:
    try:
        first = datetime.fromisoformat(first_seen)
        observed = datetime.fromisoformat(observed_at)
    except (TypeError, ValueError):
        return 0
    return max(0, (observed.date() - first.date()).days)


def merge_candidate_observation(
    existing: Mapping[str, Any],
    fresh: Mapping[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    """Refresh an undecided candidate while preserving curator-owned fields."""

    if candidate_has_decision(existing):
        return dict(existing)

    merged = dict(fresh)
    for field in _DECISION_FIELDS:
        if field in existing:
            merged[field] = existing[field]
    merged["created_at"] = existing.get("created_at") or fresh.get("created_at") or observed_at

    existing_temporal = (
        dict(existing.get("temporal"))
        if isinstance(existing.get("temporal"), Mapping)
        else {}
    )
    first_seen = str(
        existing_temporal.get("first_seen")
        or existing.get("created_at")
        or fresh.get("created_at")
        or observed_at
    )
    previous_last_seen = str(
        existing_temporal.get("last_seen")
        or existing.get("created_at")
        or ""
    )
    merged["temporal"] = {
        **existing_temporal,
        "first_seen": first_seen,
        "last_seen": observed_at,
        "status": "reobserved",
    }

    lifecycle = (
        dict(existing.get("lifecycle"))
        if isinstance(existing.get("lifecycle"), Mapping)
        else {}
    )
    try:
        observation_count = max(1, int(lifecycle.get("observation_count") or 1))
    except (TypeError, ValueError):
        observation_count = 1
    if previous_last_seen != observed_at:
        observation_count += 1
    merged["lifecycle"] = {
        **lifecycle,
        "first_observed_at": str(lifecycle.get("first_observed_at") or first_seen),
        "last_observed_at": observed_at,
        "observation_count": observation_count,
        "age_days": _age_days(first_seen, observed_at),
    }
    return merged


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    outcome: str
    candidate_id: str
    path: str = ""


@dataclass(frozen=True, slots=True)
class _CandidateLocation:
    path: Path
    index: int


class CandidateLifecycleIndex:
    """Per-run candidate index; owns no global state and flushes only touched files."""

    def __init__(self, paths: Iterable[str | Path]) -> None:
        self._files: dict[Path, list[dict[str, Any]]] = {}
        self._locations: dict[str, _CandidateLocation] = {}
        self._dirty_paths: set[Path] = set()
        for raw_path in paths:
            path = Path(raw_path)
            rows = load_candidates(path)
            self._files[path] = rows
            for index, row in enumerate(rows):
                candidate_id = str(row.get("candidate_id") or "").strip()
                if not candidate_id:
                    continue
                current = self._locations.get(candidate_id)
                if current is None:
                    self._locations[candidate_id] = _CandidateLocation(path, index)
                    continue
                current_row = self._files[current.path][current.index]
                if not candidate_has_decision(current_row) and candidate_has_decision(row):
                    self._locations[candidate_id] = _CandidateLocation(path, index)

    @classmethod
    def from_root(
        cls,
        root: str | Path,
        *,
        exclude_paths: Iterable[str | Path] = (),
    ) -> "CandidateLifecycleIndex":
        excluded = {
            Path(path).resolve(strict=False)
            for path in exclude_paths
        }
        paths = [
            path
            for path in discover_candidate_artifacts(root)
            if path.resolve(strict=False) not in excluded
        ]
        return cls(paths)

    def observe(
        self,
        candidate: Mapping[str, Any],
        *,
        observed_at: str,
    ) -> CandidateObservation:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        location = self._locations.get(candidate_id)
        if not candidate_id or location is None:
            return CandidateObservation("new", candidate_id)

        existing = self._files[location.path][location.index]
        if candidate_has_decision(existing):
            return CandidateObservation(
                "preserved_decision",
                candidate_id,
                str(location.path),
            )

        updated = merge_candidate_observation(existing, candidate, observed_at)
        if updated != existing:
            self._files[location.path][location.index] = updated
            self._dirty_paths.add(location.path)
        return CandidateObservation(
            "reused_pending",
            candidate_id,
            str(location.path),
        )

    def flush(self) -> None:
        for path in sorted(self._dirty_paths):
            write_candidates(path, self._files[path])
        self._dirty_paths.clear()
