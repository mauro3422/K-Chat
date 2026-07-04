import pytest

from src.memory.curator.recall_review import write_candidates
from src.memory.curator.curation_events import append_curation_decision
from src.memory.curator.memory_inbox import append_memory_inbox_item
from src.tools.curator_workbench import DEFINITION, run


def _candidate_path(tmp_path):
    return tmp_path / "memory" / "candidates" / "2026" / "07" / "02.recall_links.jsonl"


class FakeEntityRepo:
    def __init__(self):
        self.calls = []
        self.curated_calls = []
        self.graph_calls = []
        self.curated_rows = [
            {
                "relation_id": "rel-1",
                "source_id": "memory:user:pref",
                "target_id": "entity:kairos",
                "relation_type": "SUPPORTS",
                "weight": 0.81,
                "candidate_id": "cand-1",
                "provenance": {"source": "curator_relation_upsert"},
                "evidence": "Mauro conecto preferencia con Kairos.",
                "metadata": {"reason": "manual graph cleanup"},
            }
        ]

    async def upsert_relation(self, **kwargs):
        self.calls.append(kwargs)

    async def upsert_curated_relation(self, **kwargs):
        self.curated_calls.append(kwargs)
        return f"rel-{len(self.curated_calls)}"

    async def get_curated_relation(self, relation_id="", **kwargs):
        for row in self.curated_rows:
            if relation_id and row["relation_id"] == relation_id:
                return dict(row)
            if (
                row["source_id"] == kwargs.get("source_id")
                and row["target_id"] == kwargs.get("target_id")
                and row["relation_type"] == kwargs.get("relation_type")
                and row["candidate_id"] == kwargs.get("candidate_id", "")
            ):
                return dict(row)
        return None

    async def list_curated_relations_for_node(self, node_id, limit=20):
        return [
            dict(row)
            for row in self.curated_rows
            if row["source_id"] == node_id or row["target_id"] == node_id
        ][:limit]

    async def search_entities(self, query, limit=8):
        if "Kairos" in query or "memoria" in query:
            return [
                {"id": "entity:kairos", "name": "Kairos", "entity_type": "project"},
                {"id": "entity:memory", "name": "memoria", "entity_type": "topic"},
            ]
        return []

    async def explore_graph(self, entity_id, depth=1):
        self.graph_calls.append((entity_id, depth))
        return [
            {
                "id": entity_id,
                "name": entity_id.split(":")[-1],
                "entity_type": "project",
                "relation_type": "MENTIONS",
                "weight": 0.82,
                "depth": depth,
            }
        ]


class FakeMemoryIndex:
    async def get_all(self):
        return [
            {
                "key": "user:memory-policy",
                "value": "Mauro quiere memoria por capas con embeddings y grafo.",
                "updated_at": "2026-07-02T10:00:00",
            }
        ]


class FakeHybridResult:
    def __init__(self, source_key, text, score=0.7, rowid=10, source="memory_candidate"):
        self.source_key = source_key
        self.text = text
        self.fusion_score = score
        self.rowid = rowid
        self.source = source
        self.vector_score = score
        self.keyword_score = 0.1
        self.entity_score = 0.0
        self.rank = 1


class FakeHybridRetriever:
    async def search(self, query, top_k=8, source_filter=None):
        if source_filter == "memory":
            return [FakeHybridResult("user:semantic-memory", "Memoria canonica cercana.", 0.2, 11)]
        if source_filter == "memory_candidate":
            return [
                FakeHybridResult("abc", "Current candidate.", 0.95, 12),
                FakeHybridResult("neighbor-1", "Candidato vecino sobre memoria.", 0.72, 13),
            ]
        return []


class FakeMemoryRepos:
    def __init__(self):
        self.entity_graph = FakeEntityRepo()
        self.memory_index = FakeMemoryIndex()
        self.hybrid_retriever = FakeHybridRetriever()


class FakeRepos:
    def __init__(self):
        self.memory = FakeMemoryRepos()


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    fdef = DEFINITION["function"]
    assert fdef["name"] == "curator_workbench"
    assert "inspect" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "graph" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "explain" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "map" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "queue" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "runbook" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "preview_hints" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "materialize_hints" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "upsert_relation" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "explain_relation" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "recall_packet" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "preview_weight_policy" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "write_weight_policy_draft" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "approve_weight_policy" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "audit_weight_policy" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "audit_weight_policy_suite" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "query" in fdef["parameters"]["properties"]
    assert "source" in fdef["parameters"]["properties"]
    assert "item_id" in fdef["parameters"]["properties"]
    assert "memory_key" in fdef["parameters"]["properties"]


@pytest.mark.anyio
async def test_list_candidates(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [{"candidate_id": "abc", "status": "pending", "query": "Kairos memoria", "link_score": 0.8}],
    )

    result = await run(root=str(tmp_path), action="list")

    assert "Curator candidates" in result
    assert "abc" in result


@pytest.mark.anyio
async def test_queue_shows_prioritized_curation_commands(tmp_path):
    append_memory_inbox_item(
        {"key": "user:pref", "value": "Mauro quiere plan diario."},
        root=tmp_path,
        timestamp="2026-07-04T08:00:00",
    )

    result = await run(root=str(tmp_path), action="queue")

    assert "Curator queue" in result
    assert "inspect_inbox" in result
    assert "review_memory_inbox action=inspect" in result
    assert "curator_workbench action=runbook item_id=" in result
    assert "temporary_memory_pending_review" in result


@pytest.mark.anyio
async def test_runbook_groups_safe_and_mutating_commands(tmp_path):
    append_memory_inbox_item(
        {"key": "user:pref", "value": "Mauro quiere plan diario."},
        root=tmp_path,
        timestamp="2026-07-04T08:00:00",
    )

    result = await run(root=str(tmp_path), action="runbook")

    assert "Curator runbook" in result
    assert "Safe inspection" in result
    assert "Preview before mutation" in result
    assert "Explicit mutations" in result
    assert "Reject/fallback paths" in result
    assert "inspect: `review_memory_inbox action=inspect" in result
    assert "mutate: `review_memory_inbox action=promote" in result
    assert "fallback: `review_memory_inbox action=reject" in result


@pytest.mark.anyio
async def test_runbook_can_focus_one_queue_item(tmp_path):
    item = append_memory_inbox_item(
        {"key": "user:pref", "value": "Mauro quiere plan diario."},
        root=tmp_path,
        timestamp="2026-07-04T08:00:00",
    )

    result = await run(root=str(tmp_path), action="runbook", item_id=item["inbox_id"])

    assert "Curator runbook" in result
    assert "queue_items: `1`" in result
    assert "### Focus" in result
    assert f"id: `{item['inbox_id']}`" in result
    assert "kind: `inbox`" in result
    assert "next_action: `inspect_inbox`" in result
    assert "temporary_memory_pending_review" in result


@pytest.mark.anyio
async def test_runbook_can_focus_top_queue_item(tmp_path):
    item = append_memory_inbox_item(
        {"key": "user:pref", "value": "Mauro quiere plan diario."},
        root=tmp_path,
        timestamp="2026-07-04T08:00:00",
    )

    result = await run(root=str(tmp_path), action="runbook", item_id="top")

    assert "Curator runbook" in result
    assert "selector: `top`" in result
    assert f"id: `{item['inbox_id']}`" in result
    assert "kind: `inbox`" in result


@pytest.mark.anyio
async def test_runbook_reports_missing_queue_item(tmp_path):
    result = await run(root=str(tmp_path), action="runbook", item_id="missing")

    assert result == "[ERROR] curator queue item not found: missing"


@pytest.mark.anyio
async def test_recall_packet_combines_recall_and_queue(tmp_path):
    append_memory_inbox_item(
        {"key": "user:pref", "value": "Mauro quiere memoria con grafo."},
        root=tmp_path,
        timestamp="2026-07-04T08:00:00",
    )

    result = await run(
        root=str(tmp_path),
        action="recall_packet",
        query="memoria con grafo",
        source="memory_candidate",
        _repos=FakeRepos(),
    )

    assert "Recall packet `memoria con grafo`" in result
    assert "Resultados para" in result
    assert "`memory_candidate` uncurated" in result
    assert "Semantic relation hints" in result
    assert "candidate:abc" in result
    assert "RELATED_TO" in result
    assert "curator_workbench action=upsert_relation" in result
    assert "Curator next steps" in result
    assert "review_memory_inbox action=inspect" in result


@pytest.mark.anyio
async def test_recall_packet_requires_query(tmp_path):
    result = await run(root=str(tmp_path), action="recall_packet")

    assert result == "[ERROR] query is required."


@pytest.mark.anyio
async def test_weight_policy_actions_preview_write_and_approve(tmp_path):
    append_curation_decision(
        {"kind": "memory_candidate", "source": "remember", "action": "promote", "relation_type": "REFINES"},
        root=tmp_path,
        timestamp="2026-07-04T10:00:00",
    )
    append_curation_decision(
        {"kind": "memory_candidate", "source": "remember", "action": "promote_ready", "relation_type": "REFINES"},
        root=tmp_path,
        timestamp="2026-07-04T10:01:00",
    )
    append_curation_decision(
        {"kind": "memory_candidate", "source": "remember", "action": "complete_metadata", "missing_fields": []},
        root=tmp_path,
        timestamp="2026-07-04T10:02:00",
    )

    preview = await run(root=str(tmp_path), action="preview_weight_policy")
    written = await run(root=str(tmp_path), action="write_weight_policy_draft")
    approved = await run(
        root=str(tmp_path),
        action="approve_weight_policy",
        reason="mauro",
        evidence="reviewed",
    )

    assert "Preview retrieval weight policy draft" in preview
    assert "memory_candidate" in preview
    assert "Written retrieval weight policy draft" in written
    assert (tmp_path / "memory" / "policies" / "retrieval_weights.draft.json").exists()
    assert "Approved retrieval weight policy" in approved
    assert (tmp_path / "memory" / "policies" / "retrieval_weights.json").exists()


@pytest.mark.anyio
async def test_audit_weight_policy_compares_rankings(tmp_path):
    policy_path = tmp_path / "memory" / "policies" / "retrieval_weights.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        (
            '{"version": "v1", "status": "approved", '
            '"weights": {"memory": 1.0, "memory_candidate": 1.0}}'
        ),
        encoding="utf-8",
    )

    result = await run(
        root=str(tmp_path),
        action="audit_weight_policy",
        query="memoria",
        source="memory_candidate",
        _repos=FakeRepos(),
    )

    assert "Retrieval weight policy audit `memoria`" in result
    assert "approved_policy_version: `v1`" in result
    assert "Ranking impact" in result
    assert "memory_candidate" in result


@pytest.mark.anyio
async def test_audit_weight_policy_suite_runs_regression_queries(tmp_path):
    policy_path = tmp_path / "memory" / "policies" / "retrieval_weights.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        (
            '{"version": "v1", "status": "approved", '
            '"weights": {"memory": 1.0, "memory_candidate": 0.5}}'
        ),
        encoding="utf-8",
    )

    result = await run(
        root=str(tmp_path),
        action="audit_weight_policy_suite",
        query="memoria|grafo",
        source="memory_candidate",
        _repos=FakeRepos(),
    )

    assert "Retrieval weight policy regression suite" in result
    assert "queries: `2`" in result
    assert "source_filter: `memory_candidate`" in result
    assert "changed_queries: `2`" in result
    assert "rank_changed_queries: `0`" in result
    assert "score_changed_queries: `2`" in result
    assert "verdict: `score_shift_only`" in result
    assert "### 1. `memoria`" in result
    assert "### 2. `grafo`" in result
    assert "Next: revisar deltas de score" in result


@pytest.mark.anyio
async def test_audit_weight_policy_suite_reports_no_policy_impact(tmp_path):
    policy_path = tmp_path / "memory" / "policies" / "retrieval_weights.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        (
            '{"version": "v1", "status": "approved", '
            '"weights": {"memory": 1.0, "memory_candidate": 0.78}}'
        ),
        encoding="utf-8",
    )

    result = await run(
        root=str(tmp_path),
        action="audit_weight_policy_suite",
        query="memoria",
        source="memory_candidate",
        _repos=FakeRepos(),
    )

    assert "changed_queries: `0`" in result
    assert "max_abs_delta: `0.0`" in result
    assert "verdict: `no_policy_impact`" in result


@pytest.mark.anyio
async def test_inspect_candidate_uses_repo_for_suggestions_and_graph(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "query": "Kairos memoria por capas con embeddings",
                "relation_type": "REFINES",
                "source_id": "candidate:abc",
                "target_id": "memory:canonical",
                "target_needs_resolution": True,
                "link_score": 0.8,
            }
        ],
    )

    result = await run(
        root=str(tmp_path),
        action="inspect",
        candidate_id="abc",
        _repos=FakeRepos(),
    )

    assert "Candidate `abc`" in result
    assert "suggested_source_id: `entity:kairos`" in result
    assert "Target Suggestions" in result
    assert "memory:user:memory-policy" in result
    assert "Candidate Neighbors" in result
    assert "candidate:neighbor-1" in result
    assert "Graph source_id" in result


@pytest.mark.anyio
async def test_trace_candidate(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "query": "Kairos memoria",
                "artifact": "memory/recall/2026/07/02.jsonl",
            }
        ],
    )

    result = await run(root=str(tmp_path), action="trace", candidate_id="abc")

    assert "Source trace `abc`" in result
    assert "memory/recall/2026/07/02.jsonl" in result


@pytest.mark.anyio
async def test_explain_candidate_shows_evidence_and_next_action(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "query": "Kairos memoria por capas con embeddings",
                "relation_type": "REFINES",
                "source_id": "candidate:abc",
                "target_id": "memory:canonical",
                "target_needs_resolution": True,
                "link_score": 0.8,
                "proposed_relations": [
                    {
                        "source_id": "candidate:abc",
                        "target_id": "memory:canonical",
                        "relation_type": "REFINES",
                    }
                ],
            }
        ],
    )

    result = await run(
        root=str(tmp_path),
        action="explain",
        candidate_id="abc",
        _repos=FakeRepos(),
    )

    assert "Candidate explanation `abc`" in result
    assert "Evidence" in result
    assert "Proposed Relations" in result
    assert "Next Action" in result
    assert "action: `apply_target`" in result
    assert "target_id=memory:user:memory-policy" in result


@pytest.mark.anyio
async def test_explain_candidate_shows_metadata_completion_followup(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "query": "Kairos memoria",
                "link_score": 0.8,
            }
        ],
    )

    result = await run(root=str(tmp_path), action="explain", candidate_id="abc", _repos=FakeRepos())

    assert "action: `suggest_metadata`" in result
    assert "followup_action: `complete_metadata`" in result
    assert "action=complete_metadata" in result


@pytest.mark.anyio
async def test_graph_from_entity_id(tmp_path):
    result = await run(
        root=str(tmp_path),
        action="graph",
        entity_id="entity:kairos",
        _repos=FakeRepos(),
    )

    assert "Graph `entity:kairos`" in result
    assert "kairos" in result
    assert "```mermaid" in result
    assert "MENTIONS 0.82" in result


@pytest.mark.anyio
async def test_graph_from_memory_key_expands_to_memory_node(tmp_path):
    repos = FakeRepos()

    result = await run(
        root=str(tmp_path),
        action="graph",
        memory_key="user:memory-policy",
        depth=2,
        _repos=repos,
    )

    assert "Graph `memory:user:memory-policy`" in result
    assert "weight=0.82" in result
    assert "memory:user:memory-policy" in result
    assert "```mermaid" in result
    assert repos.memory.entity_graph.graph_calls == [("memory:user:memory-policy", 2)]


@pytest.mark.anyio
async def test_graph_from_direct_source_node(tmp_path):
    repos = FakeRepos()

    result = await run(
        root=str(tmp_path),
        action="graph",
        source_id="candidate:abc",
        _repos=repos,
    )

    assert "Graph `candidate:abc`" in result
    assert repos.memory.entity_graph.graph_calls == [("candidate:abc", 1)]


@pytest.mark.anyio
async def test_map_candidate_shows_mermaid_relation_preview(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "query": "Kairos memoria por capas con embeddings",
                "relation_type": "LINKS_TO",
                "source_id": "candidate:abc",
                "target_id": "memory:semantic-neighbor",
                "target_needs_resolution": True,
                "proposed_relations": [
                    {
                        "source_id": "candidate:abc",
                        "target_id": "memory:semantic-neighbor",
                        "relation_type": "LINKS_TO",
                        "needs_resolution": True,
                    },
                    {
                        "source_id": "candidate:abc",
                        "target_id": "entity:kairos",
                        "relation_type": "MENTIONS",
                    },
                ],
            }
        ],
    )

    result = await run(root=str(tmp_path), action="map", candidate_id="abc")

    assert "Candidate relation map `abc`" in result
    assert "edges: `2`" in result
    assert "LINKS_TO pending" in result
    assert "```mermaid" in result
    assert "LINKS_TO needs_resolution" in result


@pytest.mark.anyio
async def test_materialize_hints_writes_decision_relation_hints(tmp_path):
    append_curation_decision(
        {
            "kind": "memory_inbox",
            "action": "promote",
            "group_id": "g1",
            "relation_hints": [
                {
                    "source_id": "inbox:i1",
                    "target_id": "memory:user:lenguaje",
                    "relation_type": "PROMOTED_TO",
                }
            ],
        },
        root=tmp_path,
        timestamp="2026-07-02T10:00:00",
    )
    repos = FakeRepos()

    result = await run(root=str(tmp_path), action="materialize_hints", _repos=repos)

    assert "Materialized relation hints" in result
    assert "dry_run: `False`" in result
    assert "materialized: `1`" in result
    assert "PROMOTED_TO" in result
    assert repos.memory.entity_graph.calls[0]["source_id"] == "inbox:i1"


@pytest.mark.anyio
async def test_preview_hints_does_not_write_relation_hints(tmp_path):
    append_curation_decision(
        {
            "kind": "memory_inbox",
            "action": "promote",
            "group_id": "g1",
            "relation_hints": [
                {
                    "source_id": "inbox:i1",
                    "target_id": "memory:user:lenguaje",
                    "relation_type": "PROMOTED_TO",
                }
            ],
        },
        root=tmp_path,
        timestamp="2026-07-02T10:00:00",
    )
    repos = FakeRepos()

    result = await run(root=str(tmp_path), action="preview_hints", _repos=repos)

    assert "Preview relation hints" in result
    assert "dry_run: `True`" in result
    assert "previewed: `1`" in result
    assert "materialized: `0`" in result
    assert repos.memory.entity_graph.calls == []
    assert repos.memory.entity_graph.curated_calls == []


@pytest.mark.anyio
async def test_upsert_relation_writes_curated_relation_and_decision(tmp_path):
    repos = FakeRepos()

    result = await run(
        root=str(tmp_path),
        action="upsert_relation",
        source_id="memory:user:pref",
        target_id="entity:kairos",
        relation_type="supports",
        weight=0.81,
        evidence="Mauro conecto preferencia con Kairos.",
        reason="manual graph cleanup",
        candidate_id="cand-1",
        _repos=repos,
    )

    assert "Upserted curator relation" in result
    assert "SUPPORTS" in result
    assert "curated_relation_id" in result
    assert repos.memory.entity_graph.calls[0]["source_id"] == "memory:user:pref"
    assert repos.memory.entity_graph.calls[0]["relation_type"] == "SUPPORTS"
    assert repos.memory.entity_graph.curated_calls[0]["candidate_id"] == "cand-1"


@pytest.mark.anyio
async def test_explain_relation_by_id_shows_evidence_and_provenance(tmp_path):
    result = await run(
        root=str(tmp_path),
        action="explain_relation",
        relation_id="rel-1",
        _repos=FakeRepos(),
    )

    assert "Curated relation" in result
    assert "memory:user:pref" in result
    assert "Mauro conecto preferencia" in result
    assert "curator_relation_upsert" in result


@pytest.mark.anyio
async def test_explain_relation_lists_node_relations(tmp_path):
    result = await run(
        root=str(tmp_path),
        action="explain_relation",
        memory_key="user:pref",
        _repos=FakeRepos(),
    )

    assert "Curated relations for `memory:user:pref`" in result
    assert "rel-1" in result
    assert "SUPPORTS" in result
