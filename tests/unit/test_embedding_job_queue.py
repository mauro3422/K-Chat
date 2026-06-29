from __future__ import annotations

from src.coordination.embedding_job_queue import EmbeddingJobQueue


def test_embedding_job_queue_persists_and_drains(tmp_path):
    queue_path = tmp_path / "embedding_queue.json"
    queue = EmbeddingJobQueue(persistence_path=str(queue_path))

    queued = queue.enqueue(
        source="session",
        source_key="session-a",
        item_idx=2,
        text="User: explain remote embeddings\nAssistant: process through the primary node.",
        content_hash="abc",
        source_node="laptop",
    )

    assert queued.source_key == "session-a"
    assert len(queue) == 1

    recovered = EmbeddingJobQueue(persistence_path=str(queue_path))
    assert recovered.snapshot()[0]["source_node"] == "laptop"
    assert recovered.drain()[0].content_hash == "abc"
    assert recovered.snapshot() == []

