from src.memory.curator.conceptual_candidates import audit_candidates, candidate_id


def test_candidate_id_is_stable():
    row = {"key": "bug:temporal", "value": "Verificar timestamps."}
    assert candidate_id(row) == candidate_id(dict(row))


def test_audit_candidates_marks_high_overlap_as_duplicate():
    rows = audit_candidates(
        [{"key": "bug:temporal", "value": "Verificar timestamps de recuerdos antiguos."}],
        "Regla: verificar timestamps de recuerdos antiguos antes de llamarlos recientes.",
    )
    assert rows[0]["audit_state"] == "duplicate_possible"
