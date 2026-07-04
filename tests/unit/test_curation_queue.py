from src.memory.curator.curation_queue import build_curation_queue


def test_build_curation_queue_prioritizes_ready_promotions_and_relation_hints():
    queue = build_curation_queue(
        inbox_groups=[
            {
                "group_id": "inbox-1",
                "key": "user:pref",
                "value": "Mauro quiere plan diario.",
                "urgency": "normal",
                "reinforcement_count": 2,
                "inbox_ids": ["i1", "i2"],
                "artifacts": ["memory/inbox/2026/07/03.jsonl"],
            }
        ],
        candidate_cards=[
            {
                "candidate_id": "cand-1",
                "query": "memoria por capas",
                "recommendation": "complete_metadata",
                "score": 0.61,
                "metadata_missing": ["target_id"],
                "reasons": ["metadata_incomplete"],
                "artifact": "memory/candidates/2026/07/03.recall_links.jsonl",
                "review_command": "curator_workbench action=explain candidate_id=cand-1",
                "map_command": "",
            }
        ],
        ready_candidate_cards=[
            {
                "candidate_id": "ready-1",
                "query": "preferencia estable",
                "score": 0.74,
                "relation_type": "REFINES",
                "artifact": "memory/candidates/2026/07/03.recall_links.jsonl",
                "review_command": "curator_workbench action=explain candidate_id=ready-1",
                "relation_preview_command": "review_recall_candidate action=preview_relations candidate_id=ready-1",
                "promotion_command": "review_recall_candidate action=promote_ready candidate_id=ready-1",
            }
        ],
        curation_decisions=[
            {
                "_artifact": "memory/events/curation/2026/07/03.decisions.jsonl",
                "relation_hints": [
                    {"source_id": "inbox:i1", "target_id": "memory:user:pref", "relation_type": "PROMOTED_TO"}
                ],
            }
        ],
    )

    assert [item["kind"] for item in queue] == [
        "candidate_ready",
        "relation_hints",
        "candidate",
        "semantic_relation_hints",
        "inbox",
    ]
    assert queue[0]["next_action"] == "preview_relations"
    assert queue[0]["recommended_command"].startswith("review_recall_candidate action=preview_relations")
    assert queue[0]["followup_command"].startswith("review_recall_candidate action=promote_ready")
    assert queue[1]["next_action"] == "preview_hints"
    assert queue[1]["recommended_command"] == "curator_workbench action=preview_hints"
    assert queue[1]["followup_command"] == "curator_workbench action=materialize_hints"
    assert queue[2]["next_action"] == "complete_metadata"
    assert queue[2]["metadata_missing"] == ["target_id"]
    assert queue[3]["next_action"] == "recall_packet"
    assert queue[3]["recommended_command"].startswith("curator_workbench action=recall_packet")
    assert queue[3]["anchor_candidate_id"] == "cand-1"
    assert queue[4]["next_action"] == "inspect_inbox"
    assert queue[4]["recommended_command"].startswith("review_memory_inbox action=inspect")
    assert "include_recall_context=true" in queue[4]["recommended_command"]
    assert queue[4]["followup_command"].startswith("review_memory_inbox action=promote")
    assert queue[4]["fallback_command"].startswith("review_memory_inbox action=reject")


def test_build_curation_queue_prefers_relation_map_for_enriched_candidates():
    queue = build_curation_queue(
        candidate_cards=[
            {
                "candidate_id": "cand-graph",
                "query": "grafo memoria",
                "recommendation": "enrich",
                "score": 0.7,
                "metadata_missing": [],
                "reasons": ["needs_more_context"],
                "review_command": "curator_workbench action=explain candidate_id=cand-graph",
                "map_command": "curator_workbench action=map candidate_id=cand-graph",
            }
        ]
    )

    assert queue[0]["next_action"] == "enrich"
    assert queue[0]["recommended_command"] == "curator_workbench action=map candidate_id=cand-graph"
    assert queue[0]["why"] == ["needs_more_context"]
