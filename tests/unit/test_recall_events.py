import json

from src.memory.curator.recall_events import (
    append_recall_event,
    detect_recall_candidates,
    recall_candidates_from_events,
    recall_candidate_path,
    recall_event_path,
    recall_relation_type,
    write_recall_candidates,
)


def test_recall_event_path_uses_daily_partition(tmp_path):
    path = recall_event_path("2026-07-02T09:30:00", root=tmp_path)

    assert path == tmp_path / "memory" / "recall" / "2026" / "07" / "02.jsonl"


def test_recall_candidate_path_uses_daily_partition(tmp_path):
    path = recall_candidate_path("2026-07-02T09:30:00", root=tmp_path)

    assert path == (
        tmp_path
        / "memory"
        / "candidates"
        / "2026"
        / "07"
        / "02.recall_links.jsonl"
    )


def test_append_recall_event_writes_jsonl(tmp_path):
    path = append_recall_event(
        {"query": "memoria", "intent": "recall"},
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["timestamp"] == "2026-07-02T09:30:00"
    assert payload["query"] == "memoria"
    assert payload["intent"] == "recall"


def test_recall_relation_type_maps_link_actions():
    assert recall_relation_type("links_to") == "LINKS_TO"
    assert recall_relation_type("semantically_related") == "SEMANTICALLY_RELATED"
    assert recall_relation_type("contradicts") == "CONTRADICTS"
    assert recall_relation_type("") == "RECALLS"


def test_recall_candidates_from_events_skips_weak_auto_events():
    candidates = recall_candidates_from_events([
        {"status": "skipped", "query": "hola", "timestamp": "2026-07-02T09:30:00"},
        {
            "status": "recalled",
            "query": "Kairos memoria",
            "intent": "link",
            "trigger": "entity_with_memory_signal",
            "link_action": "links_to",
            "link_score": 0.8,
            "link_reasons": ["strong_semantic_entity_match"],
            "known_entities": ["Kairos", "Mauro"],
            "timestamp": "2026-07-02T09:31:00",
            "_artifact": "memory/recall/2026/07/02.jsonl",
        },
    ])

    assert len(candidates) == 1
    assert candidates[0]["type"] == "recall_link_candidate"
    assert candidates[0]["relation_type"] == "LINKS_TO"
    assert candidates[0]["link_score"] == 0.8
    assert candidates[0]["source_id"].startswith("candidate:")
    assert candidates[0]["target_id"] == "memory:semantic-neighbor"
    assert candidates[0]["target_needs_resolution"] is True
    assert candidates[0]["temporal"]["first_seen"] == "2026-07-02T09:31:00"
    assert candidates[0]["provenance"]["artifact"] == "memory/recall/2026/07/02.jsonl"
    assert [entity["name"] for entity in candidates[0]["entities"]] == ["Kairos", "Mauro"]


def test_recall_candidates_include_graph_relations_and_trace_metadata():
    candidates = recall_candidates_from_events([
        {
            "status": "recalled",
            "query": "recordas lo de embeddings y memoria transversal?",
            "intent": "link",
            "trigger": "explicit_recall",
            "link_action": "semantically_related",
            "link_score": 0.72,
            "link_reasons": ["explicit_memory_request"],
            "known_entities": [
                {"name": "Kairos", "entity_type": "project", "confidence": 0.82},
                "embedding",
            ],
            "result_excerpt": "Kairos necesita conectar memoria transversal con embeddings.",
            "session_id": "s1",
            "channel": "telegram",
            "timestamp": "2026-07-02T09:31:00",
            "_artifact": "memory/recall/2026/07/02.jsonl",
        },
    ])

    candidate = candidates[0]

    assert candidate["channel"] == "telegram"
    assert candidate["session_id"] == "s1"
    assert candidate["result_excerpt"].startswith("Kairos necesita")
    assert candidate["target_id"] == "memory:semantic-neighbor"
    assert candidate["target_needs_resolution"] is True
    assert candidate["provenance"]["session_id"] == "s1"
    assert candidate["provenance"]["channel"] == "telegram"
    assert candidate["entities"] == [
        {
            "name": "Kairos",
            "entity_type": "project",
            "confidence": 0.82,
            "evidence": "recall event",
        },
        {
            "name": "embedding",
            "entity_type": "unknown",
            "confidence": 0.65,
            "evidence": "recall event",
        },
    ]

    relations = candidate["proposed_relations"]
    assert {
        "source_id": candidate["source_id"],
        "target_id": "session:s1",
        "relation_type": "DERIVED_FROM",
        "weight": 0.66,
        "provenance": "recall_event_session",
    } in relations
    assert any(
        relation["relation_type"] == "SEMANTICALLY_RELATED"
        and relation["target_id"] == "memory:semantic-neighbor"
        and relation["needs_resolution"] is True
        for relation in relations
    )
    assert any(
        relation["relation_type"] == "DERIVED_FROM"
        and relation["target_id"].startswith("artifact:")
        for relation in relations
    )
    assert any(
        relation["relation_type"] == "MENTIONS"
        and relation["target_id"] == "entity:kairos"
        for relation in relations
    )


def test_recall_candidates_preserve_semantic_relation_hints():
    candidates = recall_candidates_from_events([
        {
            "status": "recalled",
            "query": "recordas memoria con grafo?",
            "intent": "recall",
            "trigger": "explicit_recall",
            "result_excerpt": "memoria con grafo",
            "timestamp": "2026-07-02T09:31:00",
            "semantic_relation_hints": [
                {
                    "source_id": "candidate:cand-1",
                    "target_id": "memory:user:memory-policy",
                    "relation_type": "REFINES",
                    "weight": 0.74,
                    "evidence": "Candidato sobre embeddings y relaciones.",
                    "provenance": "semantic_recall_neighbor",
                }
            ],
        },
    ])

    relations = candidates[0]["proposed_relations"]

    assert {
        "source_id": "candidate:cand-1",
        "target_id": "memory:user:memory-policy",
        "relation_type": "REFINES",
        "weight": 0.74,
        "provenance": "semantic_recall_neighbor",
        "evidence": "Candidato sobre embeddings y relaciones.",
    } in relations


def test_detect_recall_candidates_reads_artifact_tree(tmp_path):
    append_recall_event(
        {
            "status": "recalled",
            "query": "memoria transversal",
            "intent": "link",
            "trigger": "explicit_recall",
            "link_action": "semantically_related",
            "link_score": 0.6,
            "link_reasons": ["semantic_neighbor"],
        },
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )

    candidates = detect_recall_candidates(root=tmp_path, lookback_days=9999)

    assert len(candidates) == 1
    assert candidates[0]["relation_type"] == "SEMANTICALLY_RELATED"
    assert candidates[0]["query"] == "memoria transversal"


def test_write_recall_candidates_materializes_pending_snapshot(tmp_path):
    path = write_recall_candidates(
        [
            {
                "candidate_id": "abc123",
                "type": "recall_link_candidate",
                "relation_type": "LINKS_TO",
                "query": "Kairos memoria",
                "link_score": 0.8,
            }
        ],
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )

    assert path == (
        tmp_path
        / "memory"
        / "candidates"
        / "2026"
        / "07"
        / "02.recall_links.jsonl"
    )
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["candidate_id"] == "abc123"
    assert payload["status"] == "pending"
    assert payload["relation_type"] == "LINKS_TO"
