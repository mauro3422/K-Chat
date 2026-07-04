"""Pure helpers for curator candidate review.

This module is intentionally storage-free. Repositories, tools, and UI layers
can use it to score memory candidates without coupling curator policy to DB
or web concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CandidateSignals:
    """Signals used to rank a memory candidate for curation."""

    confidence: float = 0.0
    importance: float = 0.0
    durability: float = 0.0
    recency: float = 0.0
    reinforcement_count: int = 0
    contradiction_score: float = 0.0
    source_quality: float = 0.0
    metadata_complete: bool = False


@dataclass(frozen=True)
class CuratorRecommendation:
    """Suggested next action for a candidate."""

    action: str
    score: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RelationProposal:
    """A graph relation proposed by a curator or synthesis step."""

    source_id: str
    target_id: str
    relation_type: str
    weight: float
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LinkSignals:
    """Signals used to decide whether two memory artifacts should be linked."""

    semantic_score: float = 0.0
    entity_overlap: float = 0.0
    keyword_overlap: float = 0.0
    temporal_proximity: float = 0.0
    source_quality: float = 0.0
    contradiction_score: float = 0.0


@dataclass(frozen=True)
class RecallPolicy:
    """Decision about whether chat should retrieve memories for a message."""

    should_recall: bool
    reason: str
    query: str


def clamp01(value: float) -> float:
    """Clamp a numeric signal into the 0..1 range."""

    return max(0.0, min(1.0, float(value)))


def missing_metadata(
    metadata: Mapping[str, Any],
    required_fields: Sequence[str],
) -> tuple[str, ...]:
    """Return required metadata fields that are absent or empty."""

    missing: list[str] = []
    for field_name in required_fields:
        value = metadata.get(field_name)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(field_name)
    return tuple(missing)


def promotion_score(signals: CandidateSignals) -> float:
    """Compute a conservative promotion score for curator ordering."""

    reinforcement = clamp01(signals.reinforcement_count / 3)
    metadata_bonus = 1.0 if signals.metadata_complete else 0.0
    score = (
        clamp01(signals.confidence) * 0.22
        + clamp01(signals.importance) * 0.22
        + clamp01(signals.durability) * 0.16
        + clamp01(signals.recency) * 0.10
        + reinforcement * 0.12
        + clamp01(signals.source_quality) * 0.12
        + metadata_bonus * 0.06
        - clamp01(signals.contradiction_score) * 0.28
    )
    return round(clamp01(score), 3)


def recommend_action(signals: CandidateSignals) -> CuratorRecommendation:
    """Recommend the next curator action for a memory candidate."""

    score = promotion_score(signals)
    reasons: list[str] = []

    if signals.contradiction_score >= 0.65:
        reasons.append("contradicts_canon")
        return CuratorRecommendation("review_contradiction", score, tuple(reasons))

    if not signals.metadata_complete:
        reasons.append("metadata_incomplete")
        if score >= 0.55:
            return CuratorRecommendation("complete_metadata", score, tuple(reasons))

    if score >= 0.72:
        reasons.append("high_promotion_score")
        return CuratorRecommendation("promote", score, tuple(reasons))

    if score >= 0.45:
        reasons.append("needs_more_context")
        return CuratorRecommendation("enrich", score, tuple(reasons))

    reasons.append("low_signal")
    return CuratorRecommendation("wait_or_reject", score, tuple(reasons))


def relation_weight(
    evidence_count: int,
    confidence: float,
    source_quality: float,
    contradiction_score: float = 0.0,
) -> float:
    """Score a proposed graph relation from evidence and source quality."""

    evidence = clamp01(evidence_count / 4)
    score = (
        evidence * 0.35
        + clamp01(confidence) * 0.35
        + clamp01(source_quality) * 0.20
        - clamp01(contradiction_score) * 0.25
    )
    return round(clamp01(score), 3)


def should_recall(message: str, known_entities: Sequence[str] = ()) -> RecallPolicy:
    """Decide whether a chat message should trigger memory retrieval."""

    text = " ".join(message.lower().split())
    if not text:
        return RecallPolicy(False, "empty_message", "")

    recall_triggers = (
        "te acordas",
        "te acordas?",
        "recordas",
        "recordas?",
        "recuerdas",
        "recuerdas?",
        "remember",
        "hablamos de",
        "lo que dijimos",
        "lo de ayer",
    )
    for trigger in recall_triggers:
        if trigger in text:
            return RecallPolicy(True, "explicit_recall", message.strip())

    entity_hits = [
        entity for entity in known_entities
        if entity and entity.lower() in text
    ]
    if len(entity_hits) >= 2:
        return RecallPolicy(True, "multiple_known_entities", message.strip())

    decision_terms = (
        "prefiero",
        "decidimos",
        "bug",
        "pipeline",
        "memoria",
        "roadmap",
        "contradice",
    )
    if entity_hits and any(term in text for term in decision_terms):
        return RecallPolicy(True, "entity_with_memory_signal", message.strip())

    return RecallPolicy(False, "weak_signal", message.strip())


def link_score(signals: LinkSignals) -> float:
    """Score a semantic/graph link between memory artifacts."""

    score = (
        clamp01(signals.semantic_score) * 0.36
        + clamp01(signals.entity_overlap) * 0.22
        + clamp01(signals.keyword_overlap) * 0.16
        + clamp01(signals.temporal_proximity) * 0.10
        + clamp01(signals.source_quality) * 0.10
        - clamp01(signals.contradiction_score) * 0.22
    )
    return round(clamp01(score), 3)


def recommend_link_relation(signals: LinkSignals) -> CuratorRecommendation:
    """Recommend how a candidate should be connected to existing memory."""

    score = link_score(signals)
    reasons: list[str] = []

    if signals.contradiction_score >= 0.65:
        reasons.append("semantic_contradiction")
        return CuratorRecommendation("contradicts", score, tuple(reasons))

    if signals.semantic_score >= 0.72 and signals.entity_overlap >= 0.35:
        reasons.append("strong_semantic_entity_match")
        return CuratorRecommendation("links_to", score, tuple(reasons))

    if score >= 0.55:
        reasons.append("semantic_neighbor")
        return CuratorRecommendation("semantically_related", score, tuple(reasons))

    reasons.append("weak_link")
    return CuratorRecommendation("do_not_link", score, tuple(reasons))
