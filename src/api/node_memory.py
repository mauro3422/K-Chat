"""API helpers for LAN node memory coordination."""

from __future__ import annotations

import asyncio
from typing import Any

from src.memory.content_hash import content_hash
from src.memory.embedding_identity import session_exchange_embedding_identity


def embedding_job_dict(item: Any, *, source_node: str = "") -> dict[str, Any]:
    data = item.to_dict() if hasattr(item, "to_dict") else item.model_dump()
    if source_node and not data.get("source_node"):
        data["source_node"] = source_node
    return data


async def process_embedding_jobs(repos: Any, items: list[Any], *, source_node: str = "") -> list[dict[str, Any]]:
    """Embed or dedupe remote embedding jobs using injected repositories."""

    memory_repos = getattr(repos, "memory", None)
    store = getattr(memory_repos, "vector_store", None)
    catalog = getattr(memory_repos, "work_catalog", None)
    if store is None:
        raise RuntimeError("vector store not configured")

    from src.memory.embeddings.service import generate_embeddings_batch

    identity = session_exchange_embedding_identity()
    results: list[dict[str, Any]] = []
    pending: list[tuple[dict[str, Any], str]] = []

    for item in items:
        data = embedding_job_dict(item, source_node=source_node)
        text = str(data.get("text", ""))
        source = str(data.get("source", "session") or "session")
        source_key = str(data.get("source_key", ""))
        item_idx = int(data.get("item_idx", 0))
        text_hash = str(data.get("content_hash", "") or "") or content_hash(text)
        if not text.strip() or not source_key.strip():
            results.append({"source": source, "source_key": source_key, "item_idx": item_idx, "status": "invalid"})
            continue

        existing = store._get_conn().execute(
            "SELECT rowid FROM vec_meta WHERE content_hash = ? LIMIT 1",
            (text_hash,),
        ).fetchone()
        if existing is not None:
            rowid = int(existing[0])
            if catalog is not None:
                catalog.mark(
                    source=source,
                    source_key=source_key,
                    item_idx=item_idx,
                    content_hash=text_hash,
                    status="deduped",
                    vec_rowid=rowid,
                    reason="remote_content_hash",
                    metadata={"source_node_id": data.get("source_node", "")},
                    source_node_id=str(data.get("source_node", "")),
                    **identity.as_catalog_kwargs(),
                )
            results.append(
                {"source": source, "source_key": source_key, "item_idx": item_idx, "status": "deduped", "vec_rowid": rowid}
            )
            continue
        pending.append((data, text_hash))

    if pending:
        vectors = await asyncio.to_thread(generate_embeddings_batch, [data["text"][:4000] for data, _ in pending])
        for (data, text_hash), vec in zip(pending, vectors):
            source = str(data.get("source", "session") or "session")
            source_key = str(data.get("source_key", ""))
            item_idx = int(data.get("item_idx", 0))
            source_node = str(data.get("source_node", ""))
            rowid = store.insert(
                vec,
                source=source,
                source_key=source_key,
                exchange_idx=item_idx,
                text=str(data.get("text", ""))[:4000],
                metadata={"remote_embedding_job": True, "source_node_id": source_node},
                hash=text_hash,
                content_hash=text_hash,
                source_node_id=source_node,
            )
            if catalog is not None:
                catalog.mark(
                    source=source,
                    source_key=source_key,
                    item_idx=item_idx,
                    content_hash=text_hash,
                    status="embedded",
                    vec_rowid=rowid,
                    reason="remote_embedding_job",
                    metadata={"source_node_id": source_node},
                    source_node_id=source_node,
                    **identity.as_catalog_kwargs(),
                )
            results.append(
                {"source": source, "source_key": source_key, "item_idx": item_idx, "status": "embedded", "vec_rowid": rowid}
            )

    return results
