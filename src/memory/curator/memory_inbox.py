"""JSONL inbox artifacts for save_memory marks awaiting curation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from src.memory import paths as memory_paths
from src.memory.content_hash import content_hash
from src.memory.embedding_identity import memory_inbox_embedding_identity
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def memory_inbox_path(timestamp: str, root: str | Path | None = None) -> Path:
    """Return the daily JSONL path for memory inbox items.

    New location: ``memory/YYYY/MM/DD/inbox.jsonl``.
    """
    return memory_paths.inbox_path(target=timestamp[:10], root=root)


def inbox_item_id(item: Mapping[str, Any]) -> str:
    """Stable id for a memory inbox item."""

    raw = "|".join(
        str(item.get(name, ""))
        for name in ("created_at", "key", "value", "session_id", "message_ref")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def append_memory_inbox_item(
    item: Mapping[str, Any],
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Append a pending memory inbox item and return the payload.

    Repeated observations stay as distinct sources so the review layer can
    coalesce them and preserve their reinforcement count. Curator-generated
    semantic duplicates are filtered before reaching this persistence layer.
    """

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    payload = {
        "created_at": ts,
        "status": "pending",
        "source": "save_memory",
        "channel": "",
        "session_id": "",
        "message_ref": "",
        "urgency": "normal",
        **dict(item),
    }
    payload["inbox_id"] = str(payload.get("inbox_id") or inbox_item_id(payload))
    path = memory_inbox_path(ts, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    payload["artifact"] = str(path)
    return payload


def _load_inbox_file(path: Path) -> list[dict[str, Any]]:
    """Load all JSONL entries from a single inbox file."""
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def load_memory_inbox(
    root: str | Path | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Load inbox items from ``memory/*/*/*/inbox.jsonl``.

    ``limit=0`` means no limit. This is useful for exact-idempotency checks
    where an older pending item must not be missed just because newer dates
    contain more than the default page size.
    """

    base = Path(root) if root is not None else _project_root()
    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("memory/*/*/*/inbox.jsonl"), reverse=True):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    payload["_artifact"] = str(path)
                    items.append(payload)
                    if limit > 0 and len(items) >= limit:
                        return items
    return items


def inbox_embedding_text(item: Mapping[str, Any]) -> str:
    """Render a stable semantic text packet for an inbox item."""

    lines = [
        f"inbox_id: {item.get('inbox_id', '')}",
        f"key: {item.get('key', '')}",
        f"value: {item.get('value', '')}",
        f"channel: {item.get('channel', '')}",
        f"session_id: {item.get('session_id', '')}",
        f"message_ref: {item.get('message_ref', '')}",
        f"urgency: {item.get('urgency', '')}",
        f"status: {item.get('status', 'pending')}",
    ]
    return "\n".join(line for line in lines if line.strip() and not line.endswith(": ")).strip()


def discover_memory_inbox_embedding_items(
    root: str | Path | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Discover memory inbox items as vectorizable semantic packets."""

    items: list[dict[str, Any]] = []
    for item in load_memory_inbox(root=root, limit=limit):
        inbox_id = str(item.get("inbox_id") or "").strip()
        if not inbox_id:
            continue
        text = inbox_embedding_text(item)
        if not text:
            continue
        items.append(
            {
                "inbox_id": inbox_id,
                "path": str(item.get("_artifact") or item.get("artifact") or ""),
                "key": str(item.get("key") or ""),
                "status": str(item.get("status") or "pending"),
                "urgency": str(item.get("urgency") or "normal"),
                "text": text,
                "content_hash": content_hash(text, limit=12000),
            }
        )
    return items


def _inbox_catalog_is_processed(
    catalog: MemoryWorkCatalogRepository,
    item: Mapping[str, Any],
) -> bool:
    identity = memory_inbox_embedding_identity()
    return catalog.is_processed(
        source="memory_inbox",
        source_key=str(item.get("inbox_id") or ""),
        item_idx=-1,
        content_hash=str(item.get("content_hash") or ""),
        **identity.as_catalog_kwargs(),
    )


def _inbox_catalog_mark(
    catalog: MemoryWorkCatalogRepository,
    item: Mapping[str, Any],
    status: str,
    *,
    vec_rowid: int | None = None,
    reason: str = "",
    source_node_id: str = "",
) -> None:
    identity = memory_inbox_embedding_identity()
    catalog.mark(
        source="memory_inbox",
        source_key=str(item.get("inbox_id") or ""),
        item_idx=-1,
        content_hash=str(item.get("content_hash") or ""),
        status=status,
        vec_rowid=vec_rowid,
        reason=reason,
        metadata={
            "path": item.get("path", ""),
            "key": item.get("key", ""),
            "status": item.get("status", ""),
            "urgency": item.get("urgency", ""),
        },
        source_node_id=source_node_id,
        **identity.as_catalog_kwargs(),
    )


async def vectorize_memory_inbox_items(
    root: str | Path | None = None,
    limit: int = 1000,
    store: Any = None,
    catalog: MemoryWorkCatalogRepository | None = None,
    source_node_id: str = "",
) -> dict[str, int]:
    """Embed memory inbox items as ``source=memory_inbox``."""

    from src.memory.embeddings.service import generate_embeddings_batch

    items = discover_memory_inbox_embedding_items(root=root, limit=limit)
    result = {
        "inbox_items": len(items),
        "embedded": 0,
        "deduped": 0,
        "unchanged": 0,
        "failed": 0,
    }
    if not items:
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

    pending: list[dict[str, Any]] = []
    try:
        for item in items:
            try:
                if _inbox_catalog_is_processed(catalog, item):
                    result["unchanged"] += 1
                    continue
                existing = store._get_conn().execute(
                    "SELECT rowid FROM vec_meta WHERE content_hash = ?",
                    (item["content_hash"],),
                ).fetchone()
                if existing is not None:
                    _inbox_catalog_mark(
                        catalog,
                        item,
                        "deduped",
                        vec_rowid=int(existing[0]),
                        reason="content_hash",
                        source_node_id=source_node_id,
                    )
                    result["deduped"] += 1
                    continue
                pending.append(item)
            except Exception:
                result["failed"] += 1

        if pending:
            vectors = await asyncio.to_thread(
                generate_embeddings_batch,
                [str(item["text"])[:4000] for item in pending],
            )
            for item, vector in zip(pending, vectors):
                try:
                    rowid = store.insert(
                        vector,
                        source="memory_inbox",
                        source_key=str(item["inbox_id"]),
                        exchange_idx=-1,
                        text=str(item["text"])[:4000],
                        metadata={
                            "path": item.get("path", ""),
                            "key": item.get("key", ""),
                            "status": item.get("status", ""),
                            "urgency": item.get("urgency", ""),
                        },
                        hash=str(item["content_hash"]),
                        content_hash=str(item["content_hash"]),
                        source_node_id=source_node_id,
                    )
                    _inbox_catalog_mark(
                        catalog,
                        item,
                        "embedded",
                        vec_rowid=rowid,
                        source_node_id=source_node_id,
                    )
                    result["embedded"] += 1
                except Exception:
                    result["failed"] += 1
    finally:
        if own_store:
            store.close()

    return result
