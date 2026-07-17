"""Versioned source-layer retrieval weight policy helpers."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from src.memory.retrieval.hybrid_retriever import SourceLayerPolicy


def policy_path(root: str | Path | None = None) -> Path:
    """Return the approved retrieval weight policy path."""

    base = _base(root)
    return base / "memory" / "policies" / "retrieval_weights.json"


def draft_policy_path(root: str | Path | None = None) -> Path:
    """Return the draft retrieval weight policy path."""

    base = _base(root)
    return base / "memory" / "policies" / "retrieval_weights.draft.json"


def _base(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.getenv("KAIROS_RETRIEVAL_POLICY_ROOT", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3]


def default_weights() -> dict[str, float]:
    """Return the built-in source-layer weights."""

    return {key: float(value) for key, value in SourceLayerPolicy().weights.items()}


def _validated_weights(weights: Mapping[str, Any], *, policy_name: str) -> dict[str, float]:
    """Return finite, non-negative source weights from a policy payload."""

    normalized: dict[str, float] = {}
    for key, value in weights.items():
        source = str(key).strip()
        if not source:
            raise ValueError(f"{policy_name} weights cannot contain an empty source")
        try:
            weight = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{policy_name} weight for {source!r} must be numeric") from exc
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"{policy_name} weight for {source!r} must be finite and non-negative")
        normalized[source] = weight
    return normalized


def load_weight_policy(root: str | Path | None = None) -> dict[str, Any]:
    """Load an approved weight policy, falling back to built-in defaults."""

    path = policy_path(root)
    if not path.exists():
        return {
            "version": "builtin",
            "status": "builtin",
            "weights": default_weights(),
            "path": "",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("retrieval weight policy must be a JSON object")
    if payload.get("status") != "approved":
        raise ValueError("retrieval weight policy must have approved status")
    weights = payload.get("weights")
    if not isinstance(weights, Mapping):
        raise ValueError("retrieval weight policy must contain object weights")
    return {
        **payload,
        "weights": _validated_weights(weights, policy_name="retrieval weight policy"),
        "path": str(path),
    }


def source_layer_policy_from_file(root: str | Path | None = None) -> SourceLayerPolicy:
    """Build a SourceLayerPolicy from approved policy JSON if present."""

    payload = load_weight_policy(root)
    return SourceLayerPolicy(weights=payload["weights"])


def build_weight_policy_draft(
    recommendations: list[Mapping[str, Any]],
    *,
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a versioned draft policy from manual-review recommendations."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    current_policy = load_weight_policy(root)
    weights = dict(current_policy["weights"])
    changes: list[dict[str, Any]] = []
    for recommendation in recommendations:
        layer = str(recommendation.get("layer") or "").strip()
        if not layer:
            continue
        current = float(weights.get(layer, recommendation.get("current_weight") or 0.0))
        proposed_value = recommendation.get("proposed_weight")
        proposed = current if proposed_value is None else float(proposed_value)
        _validated_weights({layer: proposed}, policy_name="retrieval weight policy draft")
        if round(proposed - current, 6) == 0:
            continue
        weights[layer] = proposed
        changes.append(
            {
                "layer": layer,
                "source": recommendation.get("source", ""),
                "current_weight": round(current, 3),
                "proposed_weight": round(proposed, 3),
                "delta": round(proposed - current, 3),
                "sample_size": int(recommendation.get("sample_size") or 0),
                "rationale": recommendation.get("rationale", ""),
            }
        )

    return {
        "version": ts.replace(":", "").replace("-", "").replace("T", "-"),
        "status": "draft",
        "created_at": ts,
        "base_policy_version": current_policy.get("version", "builtin"),
        "apply_policy": "manual_review_required",
        "weights": {key: round(float(value), 3) for key, value in sorted(weights.items())},
        "changes": changes,
        "path": str(draft_policy_path(root)),
    }


def write_weight_policy_draft(
    recommendations: list[Mapping[str, Any]],
    *,
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Write a draft policy artifact without activating it."""

    draft = build_weight_policy_draft(recommendations, root=root, timestamp=timestamp)
    path = draft_policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**draft, "path": str(path)}


def approve_weight_policy_draft(
    *,
    root: str | Path | None = None,
    approved_by: str = "curator",
    reason: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Promote the draft policy to the approved policy file."""

    draft_path = draft_policy_path(root)
    if not draft_path.exists():
        raise FileNotFoundError(f"draft policy not found: {draft_path}")
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("draft policy must be a JSON object")
    weights = payload.get("weights")
    if not isinstance(weights, Mapping):
        raise ValueError("draft policy must contain object weights")

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    approved = {
        **payload,
        "status": "approved",
        "approved_at": ts,
        "approved_by": approved_by,
        "approval_reason": reason,
        "weights": _validated_weights(weights, policy_name="draft policy"),
    }
    path = policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approved, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**approved, "path": str(path)}


def compare_policy_rankings(
    results: list[Any],
    *,
    root: str | Path | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Compare builtin and approved source weights over retrieved results."""

    approved = load_weight_policy(root)
    builtin = default_weights()
    approved_weights = approved["weights"]
    rows: list[dict[str, Any]] = []
    for result in results[:limit]:
        source = str(getattr(result, "source", "") or "")
        source_key = str(getattr(result, "source_key", "") or "")
        text = str(getattr(result, "text", "") or "")
        base_score = float(getattr(result, "fusion_score", 0.0) or getattr(result, "score", 0.0) or 0.0)
        builtin_weight = float(builtin.get(source, SourceLayerPolicy().default_weight))
        approved_weight = float(approved_weights.get(source, builtin_weight))
        rows.append(
            {
                "source": source,
                "source_key": source_key,
                "text": text[:180],
                "base_score": round(base_score, 4),
                "builtin_weight": round(builtin_weight, 3),
                "approved_weight": round(approved_weight, 3),
                "builtin_score": round(base_score * builtin_weight, 4),
                "approved_score": round(base_score * approved_weight, 4),
                "delta": round(base_score * approved_weight - base_score * builtin_weight, 4),
            }
        )

    builtin_ranked = sorted(rows, key=lambda item: item["builtin_score"], reverse=True)
    approved_ranked = sorted(rows, key=lambda item: item["approved_score"], reverse=True)
    rank_shift: list[dict[str, Any]] = []
    builtin_positions = {
        (row["source"], row["source_key"], row["text"]): index
        for index, row in enumerate(builtin_ranked, 1)
    }
    for index, row in enumerate(approved_ranked, 1):
        identity = (row["source"], row["source_key"], row["text"])
        before = builtin_positions.get(identity, index)
        rank_shift.append({**row, "builtin_rank": before, "approved_rank": index, "rank_delta": before - index})

    return {
        "approved_policy_version": approved.get("version", "builtin"),
        "approved_policy_status": approved.get("status", "builtin"),
        "has_approved_policy": bool(approved.get("path")),
        "rows": rank_shift,
    }
