from src.memory.retrieval.graph_context import semantic_relation_hints
from src.memory.retrieval.hybrid_retriever import HybridResult


def _result(source: str, source_key: str, text: str = "evidence", score: float = 0.8) -> HybridResult:
    return HybridResult(
        rowid=1,
        text=text,
        source=source,
        source_key=source_key,
        fusion_score=score,
        rank=1,
    )


def test_semantic_relation_hints_refine_candidate_to_canon_memory():
    hints = semantic_relation_hints(
        [
            _result("memory", "user:pref", "canon", 0.9),
            _result("memory_candidate", "cand-1", "candidate refines canon", 0.75),
        ]
    )

    assert hints == [
        {
            "source_id": "candidate:cand-1",
            "target_id": "memory:user:pref",
            "relation_type": "REFINES",
            "weight": 0.75,
            "evidence": "candidate refines canon",
            "provenance": "semantic_recall_neighbor",
            "source_layer": "memory_candidate",
            "anchor_layer": "memory",
        }
    ]


def test_semantic_relation_hints_support_temporary_or_synthesis_to_canon_memory():
    inbox_hints = semantic_relation_hints(
        [
            _result("memory", "user:pref", "canon", 0.9),
            _result("memory_inbox", "inbox-1", "temporary support", 0.7),
        ]
    )
    summary_hints = semantic_relation_hints(
        [
            _result("session_summary", "s1", "summary support", 0.8),
            _result("memory", "user:pref", "canon", 0.9),
        ]
    )

    assert inbox_hints[0]["source_id"] == "inbox:inbox-1"
    assert inbox_hints[0]["target_id"] == "memory:user:pref"
    assert inbox_hints[0]["relation_type"] == "SUPPORTS"
    assert summary_hints[0]["source_id"] == "session:s1"
    assert summary_hints[0]["target_id"] == "memory:user:pref"
    assert summary_hints[0]["relation_type"] == "SUPPORTS"


def test_semantic_relation_hints_link_neighbor_candidates_without_mutating():
    hints = semantic_relation_hints(
        [
            _result("memory_candidate", "cand-1", "anchor", 0.95),
            _result("memory_candidate", "cand-2", "neighbor", 0.72),
        ]
    )

    assert hints[0]["source_id"] == "candidate:cand-1"
    assert hints[0]["target_id"] == "candidate:cand-2"
    assert hints[0]["relation_type"] == "RELATED_TO"
    assert hints[0]["weight"] == 0.72
