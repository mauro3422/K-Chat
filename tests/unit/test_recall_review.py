import json

import pytest

from src.memory.curator.curation_events import load_curation_decisions
from src.memory.curator.recall_review import (
    apply_candidate_neighbor_relation,
    apply_candidate_target,
    complete_candidate_metadata,
    load_candidates,
    mark_needs_metadata,
    promote_candidate,
    promote_ready_candidate,
    reject_candidate,
    suggest_metadata,
    write_candidates,
)


def _candidate_path(tmp_path):
    return tmp_path / "memory" / "candidates" / "2026" / "07" / "02.recall_links.jsonl"


def test_load_candidates_skips_invalid_json(tmp_path):
    path = _candidate_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"candidate_id":"a"}\nnot-json\n{"candidate_id":"b"}\n', encoding="utf-8")

    assert [c["candidate_id"] for c in load_candidates(path)] == ["a", "b"]


def test_reject_candidate_updates_status(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(path, [{"candidate_id": "abc", "status": "pending"}])

    updated = reject_candidate(
        path,
        "abc",
        "not useful",
        timestamp="2026-07-02T10:00:00",
    )

    assert updated["status"] == "rejected"
    assert updated["review_reason"] == "not useful"
    assert updated["decision_event"]["action"] == "reject"
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["reviewed_at"] == "2026-07-02T10:00:00"
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["kind"] == "memory_candidate"
    assert decisions[0]["action"] == "reject"
    assert decisions[0]["candidate_id"] == "abc"


def test_mark_needs_metadata_updates_missing_fields(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(path, [{"candidate_id": "abc", "status": "pending"}])

    updated = mark_needs_metadata(
        path,
        "abc",
        ["source_id", "target_id"],
        timestamp="2026-07-02T10:00:00",
    )

    assert updated["status"] == "needs_metadata"
    assert updated["missing_fields"] == ["source_id", "target_id"]
    assert updated["decision_event"]["action"] == "needs_metadata"
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["missing_fields"] == ["source_id", "target_id"]


def test_complete_candidate_metadata_marks_ready_and_updates_primary_relation(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "needs_metadata",
                "query": "Kairos memoria",
                "proposed_relations": [
                    {
                        "source_id": "candidate:abc",
                        "target_id": "memory:canonical",
                        "relation_type": "REFINES",
                        "needs_resolution": True,
                    }
                ],
            }
        ],
    )

    updated = complete_candidate_metadata(
        path,
        "abc",
        source_id="candidate:abc",
        target_id="memory:user:memory-policy",
        relation_type="refines",
        weight=0.74,
        reason="resolved by curator",
        timestamp="2026-07-02T10:00:00",
    )

    assert updated["status"] == "ready_for_promotion"
    assert updated["source_id"] == "candidate:abc"
    assert updated["target_id"] == "memory:user:memory-policy"
    assert updated["relation_type"] == "REFINES"
    assert updated["target_needs_resolution"] is False
    assert updated["missing_fields"] == []
    assert updated["weight"] == 0.74
    assert updated["proposed_relations"][0]["target_id"] == "memory:user:memory-policy"
    assert updated["proposed_relations"][0]["needs_resolution"] is False
    assert updated["completed_metadata"]["reason"] == "resolved by curator"
    assert updated["decision_event"]["action"] == "complete_metadata"
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["completed_fields"] == ["source_id", "target_id", "relation_type", "weight"]


def test_preview_candidate_relations_splits_promotable_and_blocked(tmp_path):
    from src.memory.curator.recall_review import preview_candidate_relations

    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "ready_for_promotion",
                "source_id": "candidate:abc",
                "target_id": "memory:user:memory-policy",
                "target_needs_resolution": False,
                "relation_type": "REFINES",
                "link_score": 0.72,
                "proposed_relations": [
                    {
                        "source_id": "candidate:cand-1",
                        "target_id": "memory:user:memory-policy",
                        "relation_type": "REFINES",
                        "weight": 0.74,
                        "evidence": "semantic neighbor evidence",
                    },
                    {
                        "source_id": "candidate:abc",
                        "target_id": "memory:semantic-neighbor",
                        "relation_type": "LINKS_TO",
                        "needs_resolution": True,
                    },
                ],
            }
        ],
    )

    preview = preview_candidate_relations(path, "abc")

    assert preview["primary"]["relation_type"] == "REFINES"
    assert preview["primary"]["needs_resolution"] is False
    assert len(preview["promotable_relations"]) == 1
    assert len(preview["blocked_relations"]) == 1
    assert "promote_ready" in preview["promote_command"]


def test_complete_candidate_metadata_keeps_candidate_blocked_when_fields_missing(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(path, [{"candidate_id": "abc", "status": "pending", "source_id": "candidate:abc"}])

    updated = complete_candidate_metadata(
        path,
        "abc",
        relation_type="SUPPORTS",
        timestamp="2026-07-02T10:00:00",
    )

    assert updated["status"] == "needs_metadata"
    assert updated["missing_fields"] == ["target_id"]
    assert updated["target_needs_resolution"] is False
    assert "proposed_relations" not in updated
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["action"] == "complete_metadata"
    assert decisions[0]["missing_fields"] == ["target_id"]


def test_apply_candidate_target_resolves_placeholder_and_marks_ready(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source_id": "candidate:abc",
                "target_id": "memory:canonical",
                "target_needs_resolution": True,
                "relation_type": "REFINES",
                "missing_fields": ["target_id"],
                "proposed_relations": [
                    {"source_id": "candidate:abc", "target_id": "session:s1", "relation_type": "DERIVED_FROM"},
                    {
                        "source_id": "candidate:abc",
                        "target_id": "memory:canonical",
                        "relation_type": "REFINES",
                        "needs_resolution": True,
                    },
                ],
            }
        ],
    )

    updated = apply_candidate_target(
        path,
        "abc",
        "memory:user:memory-policy",
        source="memory_index",
        score=0.78,
        reason="canonical_token_overlap",
        timestamp="2026-07-02T10:00:00",
    )

    assert updated["status"] == "ready_for_promotion"
    assert updated["target_id"] == "memory:user:memory-policy"
    assert updated["target_needs_resolution"] is False
    assert updated["missing_fields"] == []
    assert updated["selected_target"]["source"] == "memory_index"
    assert updated["decision_event"]["action"] == "apply_target"
    assert updated["proposed_relations"][1]["target_id"] == "memory:user:memory-policy"
    assert updated["proposed_relations"][1]["needs_resolution"] is False
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["action"] == "apply_target"
    assert decisions[0]["target_id"] == "memory:user:memory-policy"


def test_apply_candidate_neighbor_relation_records_refinement(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {"candidate_id": "abc", "status": "pending", "query": "memoria por capas"},
            {"candidate_id": "neighbor", "status": "pending", "query": "memoria embeddings"},
        ],
    )

    updated = apply_candidate_neighbor_relation(
        path,
        "abc",
        "neighbor",
        relation_type="REFINES",
        reason="same topic, more precise",
        score=0.82,
        timestamp="2026-07-02T10:00:00",
    )

    relation = updated["candidate_neighbor_relations"][0]
    assert updated["status"] == "pending"
    assert relation["source_id"] == "candidate:abc"
    assert relation["target_id"] == "candidate:neighbor"
    assert relation["relation_type"] == "REFINES"
    assert relation["weight"] == 0.82
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["action"] == "link_neighbor"
    assert decisions[0]["relation_hints"][0]["target_id"] == "candidate:neighbor"


def test_apply_candidate_neighbor_relation_marks_duplicate(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {"candidate_id": "abc", "status": "pending", "query": "memoria por capas"},
            {"candidate_id": "neighbor", "status": "pending", "query": "memoria por capas"},
        ],
    )

    updated = apply_candidate_neighbor_relation(
        path,
        "abc",
        "neighbor",
        relation_type="DUPLICATES",
        timestamp="2026-07-02T10:00:00",
    )

    assert updated["status"] == "duplicate"
    assert updated["duplicate_of"] == "neighbor"
    assert updated["review_reason"] == "semantic_candidate_duplicate"


class FakeEntityRepo:
    def __init__(self):
        self.calls = []
        self.curated_calls = []
        self.searches = []

    async def upsert_relation(self, **kwargs):
        self.calls.append(kwargs)

    async def upsert_curated_relation(self, **kwargs):
        self.curated_calls.append(kwargs)
        return "rel-123"

    async def search_entities(self, query, limit=8):
        self.searches.append((query, limit))
        if "Kairos" in query or "memoria" in query:
            return [
                {"id": "entity:kairos", "name": "Kairos", "entity_type": "project"},
                {"id": "entity:memory", "name": "memoria", "entity_type": "topic"},
            ]
        return []


@pytest.mark.anyio
async def test_promote_candidate_writes_relation_and_updates_status(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "relation_type": "LINKS_TO",
                "link_score": 0.8,
            }
        ],
    )
    repo = FakeEntityRepo()

    updated = await promote_candidate(
        path,
        "abc",
        repo,
        source_id="msg:1",
        target_id="mem:2",
        timestamp="2026-07-02T10:00:00",
    )

    assert repo.calls == [
        {
            "source_id": "msg:1",
            "target_id": "mem:2",
            "relation_type": "LINKS_TO",
            "weight": 0.8,
            "timestamp": "2026-07-02T10:00:00",
        }
    ]
    assert updated["status"] == "promoted"
    assert updated["promoted_to"] == "memory_curated_relations"
    assert updated["curated_relation_id"] == "rel-123"
    assert repo.curated_calls[0]["candidate_id"] == "abc"
    assert repo.curated_calls[0]["provenance"]["candidate_path"] == str(path)
    assert repo.curated_calls[0]["metadata"]["link_score"] == 0.8
    assert updated["decision_event"]["action"] == "promote"
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["action"] == "promote"
    assert decisions[0]["curated_relation_id"] == "rel-123"


@pytest.mark.anyio
async def test_promote_candidate_persists_resolved_proposed_relations(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source_id": "candidate:abc",
                "target_id": "memory:user:memory-policy",
                "target_needs_resolution": False,
                "relation_type": "REFINES",
                "link_score": 0.7,
                "query": "Kairos memoria",
                "proposed_relations": [
                    {
                        "source_id": "candidate:abc",
                        "target_id": "memory:user:memory-policy",
                        "relation_type": "REFINES",
                        "weight": 0.7,
                    },
                    {
                        "source_id": "candidate:abc",
                        "target_id": "session:s1",
                        "relation_type": "DERIVED_FROM",
                        "weight": 0.6,
                        "evidence": "session relation evidence",
                    },
                    {
                        "source_id": "candidate:abc",
                        "target_id": "entity:kairos",
                        "relation_type": "MENTIONS",
                        "weight": 0.8,
                    },
                    {
                        "source_id": "candidate:abc",
                        "target_id": "memory:semantic-neighbor",
                        "relation_type": "LINKS_TO",
                        "needs_resolution": True,
                    },
                ],
            }
        ],
    )

    class UniqueRelationRepo(FakeEntityRepo):
        async def upsert_curated_relation(self, **kwargs):
            self.curated_calls.append(kwargs)
            return f"rel-{len(self.curated_calls)}"

    repo = UniqueRelationRepo()

    updated = await promote_candidate(path, "abc", repo, timestamp="2026-07-02T10:00:00")

    assert updated["status"] == "promoted"
    assert [call["relation_type"] for call in repo.calls] == [
        "REFINES",
        "DERIVED_FROM",
        "MENTIONS",
        "PROMOTED_TO",
    ]
    assert len(repo.curated_calls) == 4
    assert updated["promoted_proposed_relation_ids"] == ["rel-2", "rel-3"]
    assert updated["promoted_to_relation_id"] == "rel-4"
    assert all(call["target_id"] != "memory:semantic-neighbor" for call in repo.curated_calls)
    assert repo.curated_calls[1]["evidence"] == "session relation evidence"
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["promoted_proposed_relation_ids"] == ["rel-2", "rel-3"]
    assert decisions[0]["promoted_to_relation_id"] == "rel-4"


@pytest.mark.anyio
async def test_promote_candidate_requires_metadata(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(path, [{"candidate_id": "abc", "status": "pending"}])
    repo = FakeEntityRepo()

    with pytest.raises(ValueError, match="missing metadata"):
        await promote_candidate(
            path,
            "abc",
            repo,
            timestamp="2026-07-02T10:00:00",
        )

    assert repo.calls == []
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["status"] == "needs_metadata"
    assert payload["missing_fields"] == ["source_id", "target_id", "relation_type"]


@pytest.mark.anyio
async def test_promote_candidate_blocks_unresolved_target(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source_id": "candidate:abc",
                "target_id": "memory:canonical",
                "target_needs_resolution": True,
                "relation_type": "REFINES",
            }
        ],
    )
    repo = FakeEntityRepo()

    with pytest.raises(ValueError, match="target metadata needs resolution"):
        await promote_candidate(path, "abc", repo, timestamp="2026-07-02T10:00:00")

    updated = load_candidates(path)[0]
    assert repo.calls == []
    assert updated["status"] == "needs_metadata"
    assert updated["missing_fields"] == ["target_id"]


@pytest.mark.anyio
async def test_promote_ready_candidate_requires_ready_status(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source_id": "candidate:abc",
                "target_id": "memory:user:memory-policy",
                "relation_type": "REFINES",
            }
        ],
    )
    repo = FakeEntityRepo()

    with pytest.raises(ValueError, match="candidate is not ready_for_promotion"):
        await promote_ready_candidate(path, "abc", repo, timestamp="2026-07-02T10:00:00")

    assert repo.calls == []


@pytest.mark.anyio
async def test_promote_ready_candidate_uses_resolved_metadata(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "ready_for_promotion",
                "source_id": "candidate:abc",
                "target_id": "memory:user:memory-policy",
                "target_needs_resolution": False,
                "relation_type": "REFINES",
                "link_score": 0.7,
            }
        ],
    )
    repo = FakeEntityRepo()

    updated = await promote_ready_candidate(path, "abc", repo, timestamp="2026-07-02T10:00:00")

    assert updated["status"] == "promoted"
    assert repo.calls == [
        {
            "source_id": "candidate:abc",
            "target_id": "memory:user:memory-policy",
            "relation_type": "REFINES",
            "weight": 0.7,
            "timestamp": "2026-07-02T10:00:00",
        },
        {
            "source_id": "candidate:abc",
            "target_id": "memory:user:memory-policy",
            "relation_type": "PROMOTED_TO",
            "weight": 0.7,
            "timestamp": "2026-07-02T10:00:00",
        },
    ]
    assert updated["promoted_to_relation_id"] == "rel-123"
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["promoted_to_relation_id"] == "rel-123"


@pytest.mark.anyio
async def test_promote_candidate_skips_promoted_to_trace_for_non_memory_target(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source_id": "candidate:abc",
                "target_id": "session:s1",
                "target_needs_resolution": False,
                "relation_type": "DERIVED_FROM",
                "link_score": 0.7,
            }
        ],
    )
    repo = FakeEntityRepo()

    updated = await promote_candidate(path, "abc", repo, timestamp="2026-07-02T10:00:00")

    assert updated["status"] == "promoted"
    assert [call["relation_type"] for call in repo.calls] == ["DERIVED_FROM"]
    assert updated["promoted_to_relation_id"] == ""


@pytest.mark.anyio
async def test_suggest_metadata_returns_entity_candidates(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "relation_type": "LINKS_TO",
                "query": "Kairos memoria",
            }
        ],
    )
    repo = FakeEntityRepo()

    suggestion = await suggest_metadata(path, "abc", repo)

    assert suggestion["suggested_source_id"] == "entity:kairos"
    assert suggestion["suggested_target_id"] == "entity:memory"
    assert suggestion["missing_fields"] == []
