from src.memory.curator.candidate_lifecycle import CandidateLifecycleIndex
from src.memory.curator.recall_review import load_candidates, write_candidates


def _candidate(candidate_id: str, *, status: str = "pending") -> dict:
    return {
        "candidate_id": candidate_id,
        "status": status,
        "created_at": "2026-07-02T10:00:00",
        "query": "memoria vectorial de Kairos",
        "temporal": {
            "first_seen": "2026-07-02T10:00:00",
            "last_seen": "2026-07-02T10:00:00",
            "status": "new",
        },
    }


def test_lifecycle_reuses_pending_id_and_updates_age_and_observations(tmp_path):
    path = (
        tmp_path
        / "memory"
        / "2026"
        / "07"
        / "02"
        / "candidates"
        / "session_summaries.jsonl"
    )
    write_candidates(path, [_candidate("same")])
    index = CandidateLifecycleIndex.from_root(tmp_path)

    observation = index.observe(
        {
            **_candidate("same"),
            "created_at": "2026-07-04T09:00:00",
            "query": "memoria vectorial de Kairos con grafo",
        },
        observed_at="2026-07-04T09:00:00",
    )
    index.flush()

    saved = load_candidates(path)[0]
    assert observation.outcome == "reused_pending"
    assert saved["created_at"] == "2026-07-02T10:00:00"
    assert saved["query"].endswith("con grafo")
    assert saved["temporal"]["first_seen"] == "2026-07-02T10:00:00"
    assert saved["temporal"]["last_seen"] == "2026-07-04T09:00:00"
    assert saved["lifecycle"]["age_days"] == 2
    assert saved["lifecycle"]["observation_count"] == 2


def test_lifecycle_preserves_existing_curator_decision(tmp_path):
    path = (
        tmp_path
        / "memory"
        / "2026"
        / "07"
        / "02"
        / "candidates"
        / "session_summaries.jsonl"
    )
    decided = {
        **_candidate("same", status="ready_for_promotion"),
        "decision": "promote",
    }
    write_candidates(path, [decided])
    index = CandidateLifecycleIndex.from_root(tmp_path)

    observation = index.observe(
        _candidate("same"),
        observed_at="2026-07-04T09:00:00",
    )
    index.flush()

    assert observation.outcome == "preserved_decision"
    assert load_candidates(path)[0] == decided
