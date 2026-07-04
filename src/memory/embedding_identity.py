"""Embedding pipeline identity helpers.

The work catalog uses these values as part of its idempotency check: the same
content hash is only current when it was processed by the same pipeline and
model identity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingPipelineIdentity:
    pipeline: str
    pipeline_version: str
    model_id: str
    model_version: str

    def as_catalog_kwargs(self) -> dict[str, str]:
        return {
            "pipeline": self.pipeline,
            "pipeline_version": self.pipeline_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
        }


def session_exchange_embedding_identity() -> EmbeddingPipelineIdentity:
    return EmbeddingPipelineIdentity(
        pipeline="session_exchange_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )


def memory_entry_embedding_identity() -> EmbeddingPipelineIdentity:
    return EmbeddingPipelineIdentity(
        pipeline="memory_entry_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )


def session_summary_embedding_identity() -> EmbeddingPipelineIdentity:
    return EmbeddingPipelineIdentity(
        pipeline="session_summary_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )


def transversal_synthesis_embedding_identity() -> EmbeddingPipelineIdentity:
    return EmbeddingPipelineIdentity(
        pipeline="transversal_synthesis_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )


def memory_candidate_embedding_identity() -> EmbeddingPipelineIdentity:
    return EmbeddingPipelineIdentity(
        pipeline="memory_candidate_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )


def memory_inbox_embedding_identity() -> EmbeddingPipelineIdentity:
    return EmbeddingPipelineIdentity(
        pipeline="memory_inbox_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )
