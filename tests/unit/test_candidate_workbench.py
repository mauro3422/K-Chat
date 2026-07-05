import sqlite3

import pytest

from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.curator.candidate_workbench import (
    candidate_card,
    candidate_embedding_text,
    candidate_relation_map,
    discover_candidate_files,
    discover_candidate_embedding_items,
    explain_candidate,
    inspect_candidate,
    list_candidate_cards,
    load_candidate_records,
    suggest_candidate_neighbors,
    suggest_candidate_targets,
    source_trace,
    vectorize_memory_candidates,
)
from src.memory.curator.recall_review import write_candidates


def _candidate_path(tmp_path):
    return tmp_path / "memory" / "2026" / "07" / "02" / "candidates" / "recall_links.jsonl"


class FakeEntityRepo:
    async def search_entities(self, query, limit=8):
        if "Kairos" in query or "memoria" in query:
            return [
                {"id": "entity:kairos", "name": "Kairos", "entity_type": "project"},
                {"id": "entity:memory", "name": "memoria", "entity_type": "topic"},
            ]
        return []

    async def explore_graph(self, entity_id, depth=1):
        return [
            {
                "id": entity_id,
                "name": entity_id.split(":")[-1],
                "entity_type": "project",
                "relation_type": "MENTIONS",
                "depth": depth,
            }
        ]


class FakeMemoryRepo:
    async def get_all(self):
        return [
            {
                "key": "user:memory-policy",
                "value": "Mauro quiere memoria por capas con embeddings, curadores y grafo.",
                "updated_at": "2026-07-02T10:00:00",
            },
            {
                "key": "project:unrelated",
                "value": "Otra cosa sin conexion relevante.",
                "updated_at": "2026-07-02T10:00:00",
            },
        ]


class FakeSemanticResult:
    rowid = 42
    source_key = "user:semantic-memory"
    fusion_score = 0.82
    text = "Memoria semantica sobre embeddings y grafo."


class FakeRetriever:
    async def search(self, query, top_k=8, source_filter=None):
        assert source_filter == "memory"
        return [FakeSemanticResult()]


class FakeCandidateNeighborResult:
    rowid = 77
    source_key = "neighbor-1"
    fusion_score = 0.71
    text = "Candidate packet sobre memoria por capas y curadores."


class FakeLayeredRetriever:
    def __init__(self):
        self.calls = []

    async def search(self, query, top_k=8, source_filter=None):
        self.calls.append({"query": query, "top_k": top_k, "source_filter": source_filter})
        if source_filter == "memory":
            return [FakeSemanticResult()]
        if source_filter == "memory_candidate":
            return [
                type("CurrentResult", (), {
                    "rowid": 76,
                    "source_key": "summary-1",
                    "fusion_score": 0.95,
                    "text": "Current candidate should be skipped.",
                })(),
                FakeCandidateNeighborResult(),
            ]
        return []


class FakeVectorStore:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE vec_meta (
                rowid INTEGER PRIMARY KEY,
                source TEXT,
                source_key TEXT,
                exchange_idx INTEGER,
                text TEXT,
                hash TEXT,
                content_hash TEXT,
                source_node_id TEXT DEFAULT ''
            )
            """
        )
        self.inserted: list[dict] = []

    def _get_conn(self):
        return self.conn

    def insert(self, _embedding, **kwargs) -> int:
        rowid = 30 + len(self.inserted)
        self.inserted.append(kwargs)
        self.conn.execute(
            """
            INSERT INTO vec_meta (
                rowid, source, source_key, exchange_idx, text, hash, content_hash, source_node_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                kwargs["source"],
                kwargs["source_key"],
                kwargs["exchange_idx"],
                kwargs["text"],
                kwargs["hash"],
                kwargs["content_hash"],
                kwargs.get("source_node_id", ""),
            ),
        )
        self.conn.commit()
        return rowid

    def close(self) -> None:
        self.conn.close()


def test_discover_and_load_candidate_records(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(path, [{"candidate_id": "abc", "status": "pending", "query": "Kairos memoria"}])

    files = discover_candidate_files(tmp_path)
    records = load_candidate_records(tmp_path)

    assert files == [path]
    assert records[0]["candidate_id"] == "abc"
    assert records[0]["_candidate_path"] == str(path)


def test_candidate_embedding_text_includes_relations_and_provenance(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "source": "transversal_synthesis",
                "query": "Mauro quiere memoria transversal con embeddings",
                "relation_type": "LINKS_TO",
                "source_id": "candidate:abc",
                "target_id": "memory:semantic-neighbor",
                "entities": [{"name": "Mauro"}, {"name": "memoria"}],
                "proposed_relations": [
                    {
                        "source_id": "candidate:abc",
                        "target_id": "session:s1",
                        "relation_type": "DERIVED_FROM",
                    }
                ],
                "provenance": {"session_id": "s1", "channel": "web"},
            }
        ],
    )

    candidate = load_candidate_records(tmp_path)[0]
    text = candidate_embedding_text(candidate)
    items = discover_candidate_embedding_items(tmp_path)

    assert "query: Mauro quiere memoria transversal con embeddings" in text
    assert "entities: Mauro, memoria" in text
    assert "proposed_relation: candidate:abc -[DERIVED_FROM]-> session:s1" in text
    assert items[0]["candidate_id"] == "abc"
    assert items[0]["content_hash"]


@pytest.mark.anyio
async def test_vectorize_memory_candidates_embeds_and_marks_catalog(tmp_path, monkeypatch):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source": "remember",
                "query": "Kairos memoria embeddings",
                "relation_type": "LINKS_TO",
                "source_id": "candidate:abc",
                "target_id": "memory:user-memory",
            }
        ],
    )
    store = FakeVectorStore()
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts: [[0.3] * 384 for _ in texts],
    )

    try:
        result = await vectorize_memory_candidates(
            root=tmp_path,
            store=store,
            catalog=catalog,
            source_node_id="pc",
        )
    finally:
        store.close()

    row = catalog.get(source="memory_candidate", source_key="abc", item_idx=-1)
    assert result == {"candidates": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}
    assert row is not None
    assert row["status"] == "embedded"
    assert row["pipeline"] == "memory_candidate_embedding"
    assert row["source_node_id"] == "pc"
    assert store.inserted[0]["source"] == "memory_candidate"
    assert store.inserted[0]["source_key"] == "abc"


def test_candidate_card_recommends_metadata_completion(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source": "remember",
                "query": "Kairos memoria",
                "relation_type": "LINKS_TO",
                "link_score": 0.9,
            }
        ],
    )

    card = candidate_card(load_candidate_records(tmp_path)[0])

    assert card["candidate_id"] == "abc"
    assert card["recommendation"] == "complete_metadata"
    assert "source_id" in card["metadata_missing"]
    assert card["review_command"].startswith("curator_workbench action=explain")
    assert card["promotion_command"] == ""


def test_candidate_card_exposes_session_summary_graph_hints(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "summary-1",
                "status": "pending",
                "source": "session_summary",
                "query": "Mauro quiere memoria con embeddings",
                "relation_type": "DERIVED_FROM",
                "source_id": "candidate:summary-1",
                "target_id": "session:s1",
                "link_score": 0.62,
                "entities": [
                    {"name": "Mauro", "entity_type": "person"},
                    {"name": "memoria", "entity_type": "concept"},
                ],
                "proposed_relations": [
                    {"source_id": "candidate:summary-1", "target_id": "session:s1", "relation_type": "DERIVED_FROM"},
                    {"source_id": "session:s1", "target_id": "entity:mauro", "relation_type": "MENTIONS"},
                ],
            }
        ],
    )

    card = candidate_card(load_candidate_records(tmp_path)[0])

    assert card["metadata_missing"] == []
    assert card["relation_type"] == "DERIVED_FROM"
    assert card["target_needs_resolution"] is False
    assert card["entities"] == ["Mauro", "memoria"]
    assert card["proposed_relation_count"] == 2
    assert card["map_command"].startswith("curator_workbench action=map")
    assert card["recommendation"] in {"enrich", "promote"}


def test_candidate_card_exposes_promotion_command_only_when_ready(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "ready",
                "status": "ready_for_promotion",
                "source": "transversal_synthesis",
                "query": "memoria transversal",
                "relation_type": "LINKS_TO",
                "source_id": "candidate:ready",
                "target_id": "memory:user:memory-policy",
                "target_needs_resolution": False,
                "link_score": 0.7,
            }
        ],
    )

    card = candidate_card(load_candidate_records(tmp_path)[0])

    assert card["review_command"].startswith("curator_workbench action=explain")
    assert card["map_command"] == ""
    assert card["promotion_command"].startswith("review_recall_candidate action=promote_ready")
    assert card["relation_preview_command"].startswith("review_recall_candidate action=preview_relations")


def test_list_candidate_cards_filters_status(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {"candidate_id": "pending", "status": "pending", "query": "Kairos memoria", "link_score": 0.7},
            {"candidate_id": "done", "status": "promoted", "query": "otra cosa", "link_score": 0.9},
        ],
    )

    cards = list_candidate_cards(tmp_path, status="pending")

    assert [card["candidate_id"] for card in cards] == ["pending"]


@pytest.mark.anyio
async def test_suggest_candidate_targets_uses_canonical_and_semantic_sources():
    suggestions = await suggest_candidate_targets(
        {
            "candidate_id": "summary-1",
            "target_needs_resolution": True,
            "query": "Mauro quiere memoria por capas con embeddings y grafo",
        },
        memory_repo=FakeMemoryRepo(),
        retriever=FakeRetriever(),
        limit=4,
    )

    target_ids = [item["target_id"] for item in suggestions]
    assert "memory:user:memory-policy" in target_ids
    assert "memory:user:semantic-memory" in target_ids
    assert suggestions[0]["score"] >= suggestions[-1]["score"]


@pytest.mark.anyio
async def test_suggest_candidate_neighbors_uses_memory_candidate_source():
    retriever = FakeLayeredRetriever()

    neighbors = await suggest_candidate_neighbors(
        {
            "candidate_id": "summary-1",
            "query": "Mauro quiere memoria por capas con embeddings",
        },
        retriever=retriever,
        limit=3,
    )

    assert neighbors == [
        {
            "candidate_id": "neighbor-1",
            "target_id": "candidate:neighbor-1",
            "source": "semantic_candidate",
            "rowid": 77,
            "score": 0.71,
            "reason": "semantic_candidate_neighbor",
            "text_preview": "Candidate packet sobre memoria por capas y curadores.",
            "refine_command": "",
            "duplicate_command": "",
        }
    ]
    assert retriever.calls[0]["source_filter"] == "memory_candidate"


@pytest.mark.anyio
async def test_inspect_candidate_adds_suggestions_graph_and_trace(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source": "remember",
                "query": "Kairos memoria",
                "relation_type": "LINKS_TO",
                "link_score": 0.9,
                "artifact": "memory/recall/2026/07/02.jsonl",
            }
        ],
    )

    packet = await inspect_candidate("abc", FakeEntityRepo(), root=tmp_path)

    assert packet["card"]["candidate_id"] == "abc"
    assert packet["suggestions"]["suggested_source_id"] == "entity:kairos"
    assert "source_id" in packet["graph"]
    assert packet["trace"]["candidate_path"] == str(path)


@pytest.mark.anyio
async def test_inspect_candidate_adds_target_suggestions(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "summary-1",
                "status": "pending",
                "source": "session_summary",
                "query": "Mauro quiere memoria por capas con embeddings",
                "relation_type": "REFINES",
                "source_id": "candidate:summary-1",
                "target_id": "memory:canonical",
                "target_needs_resolution": True,
                "link_score": 0.66,
            }
        ],
    )

    retriever = FakeLayeredRetriever()
    packet = await inspect_candidate(
        "summary-1",
        root=tmp_path,
        memory_repo=FakeMemoryRepo(),
        retriever=retriever,
    )

    assert packet["target_suggestions"][0]["target_id"] == "memory:user:memory-policy"
    assert packet["trace"]["target_needs_resolution"] is True
    assert packet["candidate_neighbors"][0]["target_id"] == "candidate:neighbor-1"
    assert packet["candidate_neighbors"][0]["refine_command"].startswith("review_recall_candidate action=link_neighbor")
    assert "relation_type=DUPLICATES" in packet["candidate_neighbors"][0]["duplicate_command"]
    assert {call["source_filter"] for call in retriever.calls} == {"memory", "memory_candidate"}


@pytest.mark.anyio
async def test_explain_candidate_recommends_apply_target_for_unresolved_memory_link(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "summary-1",
                "status": "pending",
                "source": "session_summary",
                "query": "Mauro quiere memoria por capas con embeddings",
                "relation_type": "REFINES",
                "source_id": "candidate:summary-1",
                "target_id": "memory:canonical",
                "target_needs_resolution": True,
                "link_score": 0.66,
                "proposed_relations": [
                    {
                        "source_id": "candidate:summary-1",
                        "target_id": "memory:canonical",
                        "relation_type": "REFINES",
                        "needs_resolution": True,
                    }
                ],
            }
        ],
    )

    explanation = await explain_candidate(
        "summary-1",
        root=tmp_path,
        memory_repo=FakeMemoryRepo(),
    )

    assert explanation["candidate_id"] == "summary-1"
    assert explanation["next_action"]["action"] == "apply_target"
    assert "target_id=memory:user:memory-policy" in explanation["next_action"]["command"]
    assert explanation["proposed_relations"][0]["relation_type"] == "REFINES"
    assert any(item["field"] == "query" for item in explanation["evidence"])


@pytest.mark.anyio
async def test_explain_candidate_recommends_metadata_completion_followup(tmp_path):
    path = _candidate_path(tmp_path)
    write_candidates(
        path,
        [
            {
                "candidate_id": "abc",
                "status": "pending",
                "source": "remember",
                "query": "Kairos memoria",
                "link_score": 0.8,
            }
        ],
    )

    explanation = await explain_candidate("abc", root=tmp_path)

    assert explanation["next_action"]["action"] == "suggest_metadata"
    assert explanation["next_action"]["followup_action"] == "complete_metadata"
    assert "action=complete_metadata" in explanation["next_action"]["followup_command"]
    assert explanation["next_action"]["missing"] == ["source_id", "target_id", "relation_type"]


def test_source_trace_includes_pattern_provenance():
    trace = source_trace(
        {
            "candidate_id": "abc",
            "_candidate_path": "memory/candidates/x.jsonl",
            "source": "tracer",
            "relation_type": "REFINES",
            "target_id": "memory:canonical",
            "target_needs_resolution": True,
            "pattern": {"session_id": "s1", "query": "Kairos"},
        }
    )

    assert trace["session_id"] == "s1"
    assert trace["relation_type"] == "REFINES"
    assert trace["target_id"] == "memory:canonical"
    assert trace["target_needs_resolution"] is True
    assert "query:Kairos" in trace["derived_from"]


def test_source_trace_includes_transversal_channel_sources():
    trace = source_trace(
        {
            "candidate_id": "abc",
            "_candidate_path": "memory/candidates/x.jsonl",
            "source": "transversal_synthesis",
            "source_channels": {"telegram": 1, "web": 1},
            "source_sessions": [
                {"session_id": "s1", "channel": "web"},
                {"session_id": "s2", "channel": "telegram"},
            ],
        }
    )

    assert trace["source_channels"] == {"telegram": 1, "web": 1}
    assert {item["session_id"] for item in trace["source_sessions"]} == {"s1", "s2"}
    assert "web:s1" in trace["derived_from"]
    assert "telegram:s2" in trace["derived_from"]


def test_candidate_relation_map_renders_proposed_relations_as_mermaid():
    relation_map = candidate_relation_map(
        {
            "candidate_id": "abc",
            "proposed_relations": [
                {
                    "source_id": "candidate:abc",
                    "target_id": "memory:semantic-neighbor",
                    "relation_type": "LINKS_TO",
                    "needs_resolution": True,
                    "weight": 0.7,
                },
                {
                    "source_id": "candidate:abc",
                    "target_id": "entity:kairos",
                    "relation_type": "MENTIONS",
                    "weight": 0.8,
                },
            ],
        }
    )

    assert relation_map["candidate_id"] == "abc"
    assert len(relation_map["nodes"]) == 3
    assert len(relation_map["edges"]) == 2
    assert relation_map["edges"][0]["needs_resolution"] is True
    assert "flowchart LR" in relation_map["mermaid"]
    assert "LINKS_TO needs_resolution" in relation_map["mermaid"]


def test_candidate_relation_map_falls_back_to_candidate_relation():
    relation_map = candidate_relation_map(
        {
            "candidate_id": "abc",
            "source_id": "candidate:abc",
            "target_id": "memory:user-memory",
            "relation_type": "REFINES",
            "target_needs_resolution": False,
            "link_score": 0.9,
        }
    )

    assert relation_map["edges"] == [
        {
            "source_id": "candidate:abc",
            "target_id": "memory:user-memory",
            "relation_type": "REFINES",
            "weight": 0.9,
            "needs_resolution": False,
            "provenance": "",
        }
    ]
