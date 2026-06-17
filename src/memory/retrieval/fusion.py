"""Fusion strategies for combining multiple retrieval signals."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FusionConfig:
    """Configuration for fusion strategy.

    Note: RRF scores with 3 signals have a theoretical max of 3/(k+1).
    With the default k=60, max RRF score ≈ 0.049. The min_score must
    be lower than this to allow RRF results to pass through.
    """
    method: str = "rrf"              # "rrf" | "weighted_sum"
    rrf_k: int = 60                  # RRF constant (k)
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3)  # vec, kw, entity
    min_score: float = 0.01          # Minimum score threshold (RRF max ~3/(k+1) ≈ 0.049)


def fuse_rrf(
    ranked_lists: list[list[int]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: fuse multiple ranked lists by rank position.

    Args:
        ranked_lists: Each is [rowid, ...] sorted by relevance (best first).
        k: RRF constant (default 60).

    Returns:
        [(rowid, rrf_score), ...] sorted by score descending.
    """
    scores: dict[int, float] = {}
    for ranks in ranked_lists:
        for pos, doc_id in enumerate(ranks):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + pos + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def fuse_weighted_sum(
    scored_lists: list[list[tuple[int, float]]],
    weights: tuple[float, float, float],
) -> list[tuple[int, float]]:
    """Weighted sum fusion: multiply each signal by its weight and sum.

    Args:
        scored_lists: Each is [(rowid, normalized_score), ...] sorted desc.
        weights: Weight for each signal (vec, kw, entity).

    Returns:
        [(rowid, total_score), ...] sorted by total descending.
    """
    scores: dict[int, float] = {}
    for signal_idx, scored in enumerate(scored_lists):
        w = weights[signal_idx] if signal_idx < len(weights) else 0.0
        for rowid, score in scored:
            scores[rowid] = scores.get(rowid, 0.0) + score * w
    return sorted(scores.items(), key=lambda x: -x[1])


def normalize_scores(
    scored: list[tuple[int, float]],
) -> list[tuple[int, float]]:
    """Min-max normalize scores to [0, 1] range.

    If all scores are equal, returns them as-is.
    """
    if not scored:
        return scored
    scores_list = [s for _, s in scored]
    min_s = min(scores_list)
    max_s = max(scores_list)
    if max_s == min_s:
        return scored
    return [(rowid, (s - min_s) / (max_s - min_s)) for rowid, s in scored]


def fuse(
    ranked_lists: list[list[int]],
    scored_lists: list[list[tuple[int, float]]] | None = None,
    config: FusionConfig | None = None,
) -> list[tuple[int, float]]:
    """Fuse multiple retrieval signals using the configured strategy.

    Args:
        ranked_lists: rowids sorted by relevance for each signal.
        scored_lists: Optional scored results for weighted_sum mode.
        config: Fusion configuration.

    Returns:
        [(rowid, score), ...] sorted by score descending.
    """
    cfg = config or FusionConfig()

    if cfg.method == "rrf":
        result = fuse_rrf(ranked_lists, k=cfg.rrf_k)
    elif cfg.method == "weighted_sum":
        if not scored_lists:
            # Fall back to RRF if no scores provided
            result = fuse_rrf(ranked_lists, k=cfg.rrf_k)
        else:
            result = fuse_weighted_sum(scored_lists, weights=cfg.weights)
    else:
        raise ValueError(f"Unknown fusion method: {cfg.method}")

    # Filter out scores below threshold
    return [(rowid, score) for rowid, score in result if score >= cfg.min_score]
