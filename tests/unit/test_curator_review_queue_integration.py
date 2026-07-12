import json

from scripts.build_curator_review_queue import build_queue
from src.memory.curator.candidate_workbench import load_candidate_records


def test_build_queue_is_visible_to_curator_workbench(tmp_path):
    (tmp_path / "MEMORY.md").write_text("Mauro prefiere revisión humana antes de promover recuerdos.", encoding="utf-8")
    conceptual = tmp_path / "memory" / "2026" / "07" / "11" / "conceptual.json"
    conceptual.parent.mkdir(parents=True)
    conceptual.write_text(json.dumps({
        "memory_candidates": [{
            "key": "decision:review-policy",
            "value": "Mantener revisión humana antes de promover recuerdos.",
            "evidence": "Declaración explícita del usuario.",
            "confidence": 0.95,
            "evidence_type": "user_statement",
            "durability": "durable",
        }]
    }, ensure_ascii=False), encoding="utf-8")

    queue_path = build_queue(tmp_path)
    records = load_candidate_records(root=tmp_path)

    assert queue_path == tmp_path / "memory" / "curator-review-queue.jsonl"
    assert len(records) == 1
    assert records[0]["source"] == "conceptual_synthesis"
    assert records[0]["candidate_id"]
