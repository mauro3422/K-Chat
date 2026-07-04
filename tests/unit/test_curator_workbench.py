from src.memory.curator.workbench import (
    CandidateSignals,
    LinkSignals,
    link_score,
    missing_metadata,
    promotion_score,
    recommend_action,
    recommend_link_relation,
    relation_weight,
    should_recall,
)


def test_missing_metadata_reports_empty_required_fields():
    metadata = {
        "session_id": "s1",
        "channel": "",
        "entities": ["Mauro"],
        "artifact": None,
    }

    assert missing_metadata(
        metadata,
        ("session_id", "channel", "entities", "artifact"),
    ) == ("channel", "artifact")


def test_promotion_score_rewards_strong_complete_candidate():
    score = promotion_score(
        CandidateSignals(
            confidence=0.95,
            importance=0.9,
            durability=0.9,
            recency=0.8,
            reinforcement_count=3,
            contradiction_score=0.0,
            source_quality=0.9,
            metadata_complete=True,
        )
    )

    assert score >= 0.85


def test_recommend_action_routes_contradictions_to_review():
    recommendation = recommend_action(
        CandidateSignals(
            confidence=0.95,
            importance=0.9,
            durability=0.9,
            recency=0.8,
            reinforcement_count=3,
            contradiction_score=0.8,
            source_quality=0.9,
            metadata_complete=True,
        )
    )

    assert recommendation.action == "review_contradiction"
    assert "contradicts_canon" in recommendation.reasons


def test_recommend_action_requires_metadata_before_promotion():
    recommendation = recommend_action(
        CandidateSignals(
            confidence=0.9,
            importance=0.9,
            durability=0.9,
            recency=0.9,
            reinforcement_count=3,
            contradiction_score=0.0,
            source_quality=0.9,
            metadata_complete=False,
        )
    )

    assert recommendation.action == "complete_metadata"


def test_relation_weight_penalizes_contradiction():
    clean = relation_weight(
        evidence_count=4,
        confidence=0.9,
        source_quality=0.9,
        contradiction_score=0.0,
    )
    contradicted = relation_weight(
        evidence_count=4,
        confidence=0.9,
        source_quality=0.9,
        contradiction_score=0.8,
    )

    assert clean > contradicted
    assert 0.0 <= contradicted <= 1.0


def test_should_recall_detects_explicit_memory_question():
    decision = should_recall("Te acordas lo que dijimos de la memoria?")

    assert decision.should_recall is True
    assert decision.reason == "explicit_recall"


def test_should_recall_detects_known_entity_with_memory_signal():
    decision = should_recall(
        "Kairos tiene que revisar el pipeline de memoria",
        known_entities=("Kairos", "Telegram"),
    )

    assert decision.should_recall is True
    assert decision.reason == "entity_with_memory_signal"


def test_link_score_combines_semantic_entity_and_keyword_signals():
    score = link_score(
        LinkSignals(
            semantic_score=0.8,
            entity_overlap=0.7,
            keyword_overlap=0.6,
            temporal_proximity=0.3,
            source_quality=0.9,
            contradiction_score=0.0,
        )
    )

    assert score >= 0.65


def test_recommend_link_relation_detects_contradiction():
    recommendation = recommend_link_relation(
        LinkSignals(
            semantic_score=0.9,
            entity_overlap=0.8,
            keyword_overlap=0.6,
            temporal_proximity=0.5,
            source_quality=0.9,
            contradiction_score=0.8,
        )
    )

    assert recommendation.action == "contradicts"
    assert "semantic_contradiction" in recommendation.reasons


def test_recommend_link_relation_detects_strong_link():
    recommendation = recommend_link_relation(
        LinkSignals(
            semantic_score=0.82,
            entity_overlap=0.5,
            keyword_overlap=0.4,
            temporal_proximity=0.2,
            source_quality=0.8,
            contradiction_score=0.0,
        )
    )

    assert recommendation.action == "links_to"
