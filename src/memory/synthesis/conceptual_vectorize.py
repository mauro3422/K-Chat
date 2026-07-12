"""Vectorization of conceptual synthesis artifacts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.memory.content_hash import content_hash
from src.memory.embedding_identity import conceptual_synthesis_embedding_identity
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository


def discover_conceptual_artifacts(root: str | Path) -> list[dict[str, str]]:
    base = Path(root)
    records = []
    for path in sorted(base.glob("memory/*/*/*/conceptual.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        records.append({"date": "-".join(path.parts[-4:-1]), "path": str(path), "text": text, "content_hash": content_hash(text, limit=200000)})
    return records


async def vectorize_conceptual_synthesis_artifacts(
    root: str | Path,
    store: Any = None,
    catalog: MemoryWorkCatalogRepository | None = None,
    source_node_id: str = "",
) -> dict[str, int]:
    from src.memory.embeddings.service import generate_embeddings_batch
    from src.memory.vector.store import VectorStore

    artifacts = discover_conceptual_artifacts(root)
    result = {"artifacts": len(artifacts), "embedded": 0, "deduped": 0, "unchanged": 0, "failed": 0}
    own_store = store is None
    store = store or VectorStore(resolve_memory_db_path())
    catalog = catalog or MemoryWorkCatalogRepository(resolve_memory_db_path())
    identity = conceptual_synthesis_embedding_identity()
    pending = []
    try:
        for item in artifacts:
            kwargs = dict(source="conceptual_synthesis", source_key=item["date"], item_idx=-1, content_hash=item["content_hash"], **identity.as_catalog_kwargs())
            if catalog.is_processed(**kwargs):
                result["unchanged"] += 1
                continue
            existing = store._get_conn().execute("SELECT rowid FROM vec_meta WHERE content_hash = ?", (item["content_hash"],)).fetchone()
            if existing:
                catalog.mark(**kwargs, status="deduped", vec_rowid=int(existing[0]), reason="content_hash", metadata={"path": item["path"]}, source_node_id=source_node_id)
                result["deduped"] += 1
            else:
                pending.append(item)
        vectors = await asyncio.to_thread(generate_embeddings_batch, [item["text"][:4000] for item in pending]) if pending else []
        for item, vector in zip(pending, vectors):
            kwargs = dict(source="conceptual_synthesis", source_key=item["date"], item_idx=-1, content_hash=item["content_hash"], **identity.as_catalog_kwargs())
            try:
                rowid = store.insert(vector, source="conceptual_synthesis", source_key=item["date"], exchange_idx=-1, text=item["text"][:4000], metadata={"path": item["path"]}, hash=item["content_hash"], content_hash=item["content_hash"], source_node_id=source_node_id)
                catalog.mark(**kwargs, status="embedded", vec_rowid=rowid, metadata={"path": item["path"]}, source_node_id=source_node_id)
                result["embedded"] += 1
            except Exception:
                result["failed"] += 1
    finally:
        if own_store:
            store.close()
    return result
