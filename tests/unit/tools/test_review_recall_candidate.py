import pytest

from src.memory.curator.recall_review import write_candidates
from src.tools.review_recall_candidate import DEFINITION, run


def _candidate_path(tmp_path):
    return tmp_path / "memory" / "candidates" / "2026" / "07" / "02.recall_links.jsonl"


class TestReviewRecallCandidateDefinition:
    def test_definition_structure(self):
        assert DEFINITION["type"] == "function"
        fdef = DEFINITION["function"]
        assert fdef["name"] == "review_recall_candidate"
        assert "path" in fdef["parameters"]["required"]
        assert "promote" in fdef["parameters"]["properties"]["action"]["enum"]
        assert "promote_ready" in fdef["parameters"]["properties"]["action"]["enum"]
        assert "apply_target" in fdef["parameters"]["properties"]["action"]["enum"]
        assert "complete_metadata" in fdef["parameters"]["properties"]["action"]["enum"]
        assert "preview_relations" in fdef["parameters"]["properties"]["action"]["enum"]
        assert "link_neighbor" in fdef["parameters"]["properties"]["action"]["enum"]
        assert "suggest_metadata" in fdef["parameters"]["properties"]["action"]["enum"]


class FakeEntityRepo:
    def __init__(self):
        self.calls = []
        self.curated_calls = []

    async def upsert_relation(self, **kwargs):
        self.calls.append(kwargs)

    async def upsert_curated_relation(self, **kwargs):
        self.curated_calls.append(kwargs)
        return "rel-123"

    async def search_entities(self, query, limit=8):
        if "Kairos" in query or "memoria" in query:
            return [
                {"id": "entity:kairos", "name": "Kairos", "entity_type": "project"},
                {"id": "entity:memory", "name": "memoria", "entity_type": "topic"},
            ]
        return []


class TestReviewRecallCandidateRun:
    @pytest.mark.anyio
    async def test_list_candidates(self, tmp_path):
        path = _candidate_path(tmp_path)
        write_candidates(
            path,
            [
                {
                    "candidate_id": "abc",
                    "status": "pending",
                    "relation_type": "LINKS_TO",
                    "query": "Kairos memoria",
                    "link_score": 0.8,
                }
            ],
        )

        result = await run(path=str(path))

        assert "Recall candidates" in result
        assert "abc" in result
        assert "LINKS_TO" in result

    @pytest.mark.anyio
    async def test_reject_candidate(self, tmp_path):
        path = _candidate_path(tmp_path)
        write_candidates(path, [{"candidate_id": "abc", "status": "pending"}])

        result = await run(
            path=str(path),
            action="reject",
            candidate_id="abc",
            reason="bad link",
        )

        assert "[OK]" in result
        assert "Rejected" in result

    @pytest.mark.anyio
    async def test_suggest_metadata_uses_entity_graph(self, tmp_path):
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

        class Memory:
            entity_graph = repo

        class Repos:
            memory = Memory()

        result = await run(
            path=str(path),
            action="suggest_metadata",
            candidate_id="abc",
            _repos=Repos(),
        )

        assert "Metadata suggestions" in result
        assert "entity:kairos" in result
        assert "entity:memory" in result

    @pytest.mark.anyio
    async def test_apply_target_marks_candidate_ready(self, tmp_path):
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
                    "link_score": 0.7,
                }
            ],
        )

        result = await run(
            path=str(path),
            action="apply_target",
            candidate_id="abc",
            target_id="memory:user:memory-policy",
            target_source="memory_index",
            target_score=0.81,
            target_reason="canonical_token_overlap",
        )

        assert "[OK]" in result
        assert "ready_for_promotion" in result
        assert "memory:user:memory-policy" in result

    @pytest.mark.anyio
    async def test_complete_metadata_marks_candidate_ready(self, tmp_path):
        path = _candidate_path(tmp_path)
        write_candidates(
            path,
            [
                {
                    "candidate_id": "abc",
                    "status": "needs_metadata",
                    "query": "Kairos memoria",
                }
            ],
        )

        result = await run(
            path=str(path),
            action="complete_metadata",
            candidate_id="abc",
            source_id="candidate:abc",
            target_id="memory:user:memory-policy",
            relation_type="REFINES",
            weight=0.73,
            reason="curator resolved metadata",
        )

        assert "[OK]" in result
        assert "Completed metadata" in result
        assert "ready_for_promotion" in result

    @pytest.mark.anyio
    async def test_preview_relations_shows_promotable_and_blocked_relations(self, tmp_path):
        path = _candidate_path(tmp_path)
        write_candidates(
            path,
            [
                {
                    "candidate_id": "abc",
                    "status": "ready_for_promotion",
                    "source_id": "candidate:abc",
                    "target_id": "memory:user:memory-policy",
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

        result = await run(
            path=str(path),
            action="preview_relations",
            candidate_id="abc",
        )

        assert "Relation preview `abc`" in result
        assert "semantic neighbor evidence" in result
        assert "promotable: `1`" in result
        assert "blocked: `1`" in result
        assert "promote_ready" in result

    @pytest.mark.anyio
    async def test_complete_metadata_reports_remaining_missing_fields(self, tmp_path):
        path = _candidate_path(tmp_path)
        write_candidates(path, [{"candidate_id": "abc", "status": "pending"}])

        result = await run(
            path=str(path),
            action="complete_metadata",
            candidate_id="abc",
            source_id="candidate:abc",
        )

        assert "[OK]" in result
        assert "needs_metadata" in result
        assert "missing=target_id, relation_type" in result

    @pytest.mark.anyio
    async def test_link_neighbor_records_candidate_relation(self, tmp_path):
        path = _candidate_path(tmp_path)
        write_candidates(
            path,
            [
                {"candidate_id": "abc", "status": "pending"},
                {"candidate_id": "neighbor", "status": "pending"},
            ],
        )

        result = await run(
            path=str(path),
            action="link_neighbor",
            candidate_id="abc",
            neighbor_candidate_id="neighbor",
            relation_type="REFINES",
            reason="near duplicate",
        )

        assert "[OK]" in result
        assert "REFINES" in result
        assert "neighbor" in result

    @pytest.mark.anyio
    async def test_promote_candidate_uses_injected_repo(self, tmp_path):
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

        class Memory:
            entity_graph = repo

        class Repos:
            memory = Memory()

        result = await run(
            path=str(path),
            action="promote",
            candidate_id="abc",
            source_id="msg:1",
            target_id="mem:2",
            _repos=Repos(),
        )

        assert "[OK]" in result
        assert repo.calls[0]["source_id"] == "msg:1"
        assert repo.calls[0]["target_id"] == "mem:2"
        assert repo.curated_calls[0]["candidate_id"] == "abc"

    @pytest.mark.anyio
    async def test_promote_candidate_reports_missing_metadata(self, tmp_path):
        path = _candidate_path(tmp_path)
        write_candidates(path, [{"candidate_id": "abc", "status": "pending"}])
        repo = FakeEntityRepo()

        class Memory:
            entity_graph = repo

        class Repos:
            memory = Memory()

        result = await run(
            path=str(path),
            action="promote",
            candidate_id="abc",
            _repos=Repos(),
        )

        assert "[ERROR]" in result
        assert "missing metadata" in result
        assert repo.calls == []

    @pytest.mark.anyio
    async def test_promote_candidate_reports_unresolved_target(self, tmp_path):
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

        class Memory:
            entity_graph = repo

        class Repos:
            memory = Memory()

        result = await run(
            path=str(path),
            action="promote",
            candidate_id="abc",
            _repos=Repos(),
        )

        assert "[ERROR]" in result
        assert "target metadata needs resolution" in result
        assert repo.calls == []

    @pytest.mark.anyio
    async def test_promote_ready_candidate_uses_resolved_metadata(self, tmp_path):
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
                }
            ],
        )
        repo = FakeEntityRepo()

        class Memory:
            entity_graph = repo

        class Repos:
            memory = Memory()

        result = await run(
            path=str(path),
            action="promote_ready",
            candidate_id="abc",
            _repos=Repos(),
        )

        assert "[OK]" in result
        assert "Promoted ready candidate" in result
        assert repo.calls[0]["source_id"] == "candidate:abc"
        assert repo.calls[0]["target_id"] == "memory:user:memory-policy"

    @pytest.mark.anyio
    async def test_promote_ready_candidate_reports_pending_status(self, tmp_path):
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

        class Memory:
            entity_graph = repo

        class Repos:
            memory = Memory()

        result = await run(
            path=str(path),
            action="promote_ready",
            candidate_id="abc",
            _repos=Repos(),
        )

        assert "[ERROR]" in result
        assert "candidate is not ready_for_promotion" in result
        assert repo.calls == []
