"""Session summary vectorization."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.memory.embedding_identity import session_summary_embedding_identity

logger = logging.getLogger(__name__)


def _summary_catalog_is_processed(
    catalog: "MemoryWorkCatalogRepository",
    artifact: "Mapping[str, Any]",
) -> bool:
    identity = session_summary_embedding_identity()
    return catalog.is_processed(
        source="session_summary",
        source_key=str(artifact.get("session_id") or ""),
        item_idx=-1,
        content_hash=str(artifact.get("content_hash") or ""),
        **identity.as_catalog_kwargs(),
    )


def _summary_catalog_mark(
    catalog: "MemoryWorkCatalogRepository",
    artifact: "Mapping[str, Any]",
    status: str,
    *,
    vec_rowid: int | None = None,
    reason: str = "",
    source_node_id: str = "",
) -> None:
    identity = session_summary_embedding_identity()
    catalog.mark(
        source="session_summary",
        source_key=str(artifact.get("session_id") or ""),
        item_idx=-1,
        content_hash=str(artifact.get("content_hash") or ""),
        status=status,
        vec_rowid=vec_rowid,
        reason=reason,
        metadata={
            "path": artifact.get("path", ""),
            "channel": artifact.get("channel", "web"),
        },
        source_node_id=source_node_id,
        **identity.as_catalog_kwargs(),
    )


async def vectorize_session_summary_artifacts(
    root: str | "Path" | None = None,
    store: Any = None,
    catalog: "MemoryWorkCatalogRepository | None" = None,
    source_node_id: str = "",
) -> dict[str, int]:
    """Embed session summary artifacts as ``source=session_summary``."""

    from src.memory.embeddings.service import generate_embeddings_batch
    from src.memory.memory_db_path import resolve_memory_db_path
    from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
    from src.memory.synthesis.session import discover_session_summary_artifacts

    artifacts = discover_session_summary_artifacts(root=root)
    result = {
        "artifacts": len(artifacts),
        "embedded": 0,
        "deduped": 0,
        "unchanged": 0,
        "failed": 0,
    }
    if not artifacts:
        return result

    own_store = False
    if store is None:
        from src.memory.vector.store import VectorStore

        store = VectorStore(resolve_memory_db_path())
        own_store = True
    catalog = catalog or MemoryWorkCatalogRepository(resolve_memory_db_path())

    if not source_node_id:
        from src.memory.provenance import resolve_local_node_id

        source_node_id = resolve_local_node_id()

    candidates: list[dict[str, Any]] = []
    try:
        for artifact in artifacts:
            try:
                if _summary_catalog_is_processed(catalog, artifact):
                    result["unchanged"] += 1
                    continue
                existing = store._get_conn().execute(
                    "SELECT rowid FROM vec_meta WHERE content_hash = ?",
                    (artifact["content_hash"],),
                ).fetchone()
                if existing is not None:
                    _summary_catalog_mark(
                        catalog,
                        artifact,
                        "deduped",
                        vec_rowid=int(existing[0]),
                        reason="content_hash",
                        source_node_id=source_node_id,
                    )
                    result["deduped"] += 1
                    continue
                candidates.append(artifact)
            except Exception:
                logger.exception("Failed to check dedup for artifact %s", artifact.get("session_id", "?"))
                result["failed"] += 1

        if candidates:
            vectors = await asyncio.to_thread(
                generate_embeddings_batch,
                [str(item["text"])[:4000] for item in candidates],
            )
            for artifact, vector in zip(candidates, vectors):
                try:
                    rowid = store.insert(
                        vector,
                        source="session_summary",
                        source_key=str(artifact["session_id"]),
                        exchange_idx=-1,
                        text=str(artifact["text"])[:4000],
                        metadata={
                            "path": artifact.get("path", ""),
                            "channel": artifact.get("channel", "web"),
                        },
                        hash=str(artifact["content_hash"]),
                        content_hash=str(artifact["content_hash"]),
                        source_node_id=source_node_id,
                    )
                    _summary_catalog_mark(
                        catalog,
                        artifact,
                        "embedded",
                        vec_rowid=rowid,
                        source_node_id=source_node_id,
                    )
                    result["embedded"] += 1
                except Exception:
                    logger.exception("Failed to insert embedding for artifact %s", artifact.get("session_id", "?"))
                    result["failed"] += 1
    finally:
        if own_store:
            store.close()

    return result
