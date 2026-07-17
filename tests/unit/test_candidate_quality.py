import pytest

from src.memory.curator.candidate_quality import (
    candidate_has_sufficient_signal,
    evaluate_candidate_signal,
)


@pytest.mark.parametrize(
    ("signal", "reason"),
    [
        ("solo", "generic_stopword"),
        ("cada", "generic_stopword"),
        ("lado", "generic_stopword"),
        ("está", "generic_stopword"),
        ("est\ufffd", "damaged_encoding"),
        ("abc", "too_short"),
        ("1234", "generic_stopword"),
        ("---", "too_short"),
    ],
)
def test_candidate_quality_rejects_low_signal_tokens(signal, reason):
    result = evaluate_candidate_signal(signal)

    assert result.accepted is False
    assert result.reason == reason


def test_candidate_quality_preserves_valid_semantic_candidate():
    result = evaluate_candidate_signal("memoria_vectorial")

    assert result.accepted is True
    assert result.semantic_tokens == ("memoria_vectorial",)


def test_candidate_quality_never_hides_existing_curator_decision():
    assert candidate_has_sufficient_signal(
        {
            "candidate_id": "decided",
            "status": "rejected",
            "topic": "solo",
        }
    ) is True


def test_candidate_quality_accepts_conceptual_candidate_value():
    assert candidate_has_sufficient_signal(
        {
            "candidate_id": "conceptual",
            "status": "pending",
            "key": "user:request-memory-audit",
            "value": "El usuario pidió una auditoría completa de la memoria.",
        }
    ) is True
