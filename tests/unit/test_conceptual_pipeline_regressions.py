from datetime import date

import pytest

from src.memory.embedding_identity import conceptual_synthesis_embedding_identity
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.synthesis.conceptual import validate_memory_candidates
from src.memory.synthesis.conceptual_vectorize import vectorize_conceptual_synthesis_artifacts
from src.memory.vector.store import VectorStore


def test_candidate_validation_rejects_non_numeric_confidence():
    result = validate_memory_candidates({
        "memory_candidates": [{
            "key": "decision:review-policy",
            "value": "Mantener revisión humana antes de promover recuerdos.",
            "evidence": "Decisión explícita del usuario.",
            "confidence": "alta",
            "evidence_type": "user_statement",
            "durability": "durable",
        }]
    })

    assert result["memory_candidates"] == []
    assert result["rejected_memory_candidates"] == [{
        "key": "decision:review-policy",
        "reason": "invalid_confidence",
    }]


@pytest.mark.anyio
async def test_conceptual_vectorization_uses_real_store_and_is_idempotent(tmp_path, monkeypatch):
    target = date(2026, 7, 11)
    artifact = tmp_path / "memory" / "2026" / "07" / "11" / "conceptual.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Síntesis conceptual\n\n- Mantener revisión humana.\n", encoding="utf-8")

    db_path = tmp_path / "memory.db"
    store = VectorStore(str(db_path))
    catalog = MemoryWorkCatalogRepository(str(db_path))
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts: [[0.1] * 384 for _ in texts],
    )

    try:
        first = await vectorize_conceptual_synthesis_artifacts(
            root=tmp_path,
            store=store,
            catalog=catalog,
            source_node_id="pc",
        )
        second = await vectorize_conceptual_synthesis_artifacts(
            root=tmp_path,
            store=store,
            catalog=catalog,
            source_node_id="pc",
        )
    finally:
        store.close()

    identity = conceptual_synthesis_embedding_identity()
    row = catalog.get(
        source="conceptual_synthesis",
        source_key=target.isoformat(),
        item_idx=-1,
        **identity.as_catalog_kwargs(),
    )
    assert first == {"artifacts": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}
    assert second == {"artifacts": 1, "embedded": 0, "deduped": 0, "unchanged": 1, "failed": 0}
    assert row is not None
    assert row["status"] == "embedded"
    assert row["source_node_id"] == "pc"
