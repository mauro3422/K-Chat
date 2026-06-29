"""LAN node memory coordination endpoints.

Split from ``node.py`` — keeps the distributed-memory domain (write queue,
lease-based snapshots, sync status, diagnostics). URLs unchanged, registered
under the same ``/api/node`` prefix via auto-discovery.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.coordination.embedding_job_queue import get_embedding_job_queue
from src.coordination.memory_write_queue import apply_pending_memory_writes
from src.memory.content_hash import content_hash
from src.memory.embedding_identity import session_exchange_embedding_identity
from web.routers._memory_snapshot import build_memory_snapshot, relay_memory_event
from web.routers._node_helpers import (
    _get_coordinator,
    _get_event_bus,
    _get_leader_lease_manager,
    _get_memory_queue,
    _get_node_bridge,
    _get_save_memory_run,
    _peer_cluster_state,
)
from web.routers._node_models import NodeEmbeddingJobPayload, NodeMemoryWritePayload
from web.services.node_observability import _memory_observability

router = APIRouter(prefix="/api/node")


def _get_embedding_queue(request: Request):
    return getattr(request.app.state, "embedding_job_queue", None) or get_embedding_job_queue(
        getattr(request.app.state, "config", None)
    )


def _embedding_job_dict(item: Any, *, source_node: str = "") -> dict[str, Any]:
    data = item.to_dict() if hasattr(item, "to_dict") else item.model_dump()
    if source_node and not data.get("source_node"):
        data["source_node"] = source_node
    return data


async def _process_embedding_jobs(request: Request, items: list[Any], *, source_node: str = "") -> list[dict[str, Any]]:
    repos = getattr(request.app.state, "repos", None)
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
        data = _embedding_job_dict(item, source_node=source_node)
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
            results.append({"source": source, "source_key": source_key, "item_idx": item_idx, "status": "deduped", "vec_rowid": rowid})
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
            results.append({"source": source, "source_key": source_key, "item_idx": item_idx, "status": "embedded", "vec_rowid": rowid})

    return results


@router.post("/memory/request")
async def memory_request(payload: NodeMemoryWritePayload, request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    config = getattr(request.app.state, "config", None)
    preferred_role = str(getattr(config, "node_role", "secondary"))
    if not await coordinator.is_primary():
        queue = _get_memory_queue(request)
        queued = queue.enqueue(payload.key, payload.value, source_node=str(payload.source.get("node_id", "")), reason="primary_unavailable")
        await _get_event_bus(request).publish(
            "memory_write_queued",
            {"key": payload.key, "source": payload.source, "state": queue.snapshot()},
        )
        return JSONResponse({"ok": True, "granted": False, "queued": True, "request": queued.to_dict()})

    started = time.perf_counter()
    result = await _get_save_memory_run(request)(
        key=payload.key,
        value=payload.value,
        _repos=getattr(request.app.state, "repos", None),
        _force_local_write=True,
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    if result.startswith("[OK]"):
        replay_request = None
        if preferred_role != "primary":
            queue = _get_memory_queue(request)
            replay_request = queue.enqueue(
                payload.key,
                payload.value,
                source_node=coordinator.node_id,
                reason="failover_replay_to_preferred_primary",
            )
        await coordinator.mark_memory_revision({"event": "memory_request", "key": payload.key})
        await coordinator.mark_memory_sync({"event": "memory_request", "key": payload.key})
        completion_event = {
            "key": payload.key,
            "value": payload.value,
            "source": payload.source,
            "node_id": coordinator.node_id,
            "result": result,
        }
        bus = _get_event_bus(request)
        await bus.publish("memory_synced", completion_event)
        await bus.publish("memory_write_completed", completion_event)
        try:
            bridge = _get_node_bridge(request)
            await bridge.broadcast_event("memory_write_completed", completion_event)
        except Exception:
            pass
    response = {"ok": True, "granted": True, "queued": False, "status": "completed", "duration_ms": duration_ms, "result": result}
    if result.startswith("[OK]") and preferred_role != "primary":
        response["replay_queued"] = True
        response["replay_request"] = replay_request.to_dict() if replay_request is not None else None
    return JSONResponse(response)


@router.get("/memory/queue")
async def memory_queue(request: Request) -> JSONResponse:
    queue = _get_memory_queue(request)
    return JSONResponse({"ok": True, "pending": queue.snapshot()})


@router.post("/memory/flush")
async def memory_flush(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    if not await coordinator.is_primary():
        return JSONResponse({"ok": False, "error": "primary only"}, status_code=403)

    results = await apply_pending_memory_writes(
        _get_memory_queue(request),
        _get_save_memory_run(request),
        repos=getattr(request.app.state, "repos", None),
    )
    if results:
        await _get_event_bus(request).publish("memory_synced", {"applied": results, "source": "flush"})
    return JSONResponse({"ok": True, "applied": results, "pending": []})


@router.post("/embeddings/jobs")
async def embedding_jobs(payload: NodeEmbeddingJobPayload, request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    source_node = str(payload.source.get("node_id", ""))
    if payload.dry_run:
        return JSONResponse({
            "ok": True,
            "queued": False,
            "dry_run": True,
            "accepted": len(payload.items),
            "processed": [
                {
                    "source": item.source,
                    "source_key": item.source_key,
                    "item_idx": item.item_idx,
                    "status": "dry_run",
                }
                for item in payload.items
            ],
        })
    if not await coordinator.is_primary():
        queue = _get_embedding_queue(request)
        queued = [
            queue.enqueue(
                source=item.source,
                source_key=item.source_key,
                item_idx=item.item_idx,
                text=item.text,
                content_hash=item.content_hash,
                source_node=source_node,
                reason="primary_unavailable",
            ).to_dict()
            for item in payload.items
        ]
        return JSONResponse({"ok": True, "queued": True, "accepted": len(queued), "pending": queue.snapshot()})

    started = time.perf_counter()
    results = await _process_embedding_jobs(request, list(payload.items), source_node=source_node)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    return JSONResponse({"ok": True, "queued": False, "processed": results, "duration_ms": duration_ms})


@router.get("/embeddings/queue")
async def embedding_queue(request: Request) -> JSONResponse:
    queue = _get_embedding_queue(request)
    return JSONResponse({"ok": True, "pending": queue.snapshot(), "path": getattr(queue, "persistence_path", "")})


@router.post("/embeddings/flush")
async def embedding_flush(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    if not await coordinator.is_primary():
        return JSONResponse({"ok": False, "error": "primary only"}, status_code=403)
    queue = _get_embedding_queue(request)
    pending = queue.drain()
    try:
        results = await _process_embedding_jobs(request, pending)
    except Exception as exc:
        for item in pending:
            queue.mark_retryable(item, error=str(exc))
        return JSONResponse({"ok": False, "error": str(exc), "pending": queue.snapshot()}, status_code=503)
    return JSONResponse({"ok": True, "processed": results, "pending": []})


@router.get("/sync/status")
async def sync_status(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    queue = _get_memory_queue(request)
    embedding_queue = _get_embedding_queue(request)
    lease_manager = _get_leader_lease_manager(request)
    lease = lease_manager.snapshot()
    bridge = _get_node_bridge(request)
    cluster = await _peer_cluster_state(request)
    snapshot = coordinator.snapshot()
    now = time.time()
    return JSONResponse(
        {
            "ok": True,
            "node": snapshot,
            "bridge": {
                "base_url": bridge.base_url,
                "peer_urls": bridge.peer_urls,
            },
            "cluster": cluster,
            "lease": lease.to_dict() if lease else None,
            "queue": {
                "size": len(queue),
                "pending": queue.snapshot(),
                "path": getattr(queue, "persistence_path", ""),
            },
            "embedding_queue": {
                "size": len(embedding_queue),
                "pending": embedding_queue.snapshot(),
                "path": getattr(embedding_queue, "persistence_path", ""),
            },
            "sync": {
                "role": snapshot.get("role", ""),
                "is_primary": await coordinator.is_primary(),
                "has_recent_primary": snapshot.get("has_recent_primary", False),
                "memory_is_fresh": snapshot.get("memory_is_fresh", False),
                "last_memory_revision": snapshot.get("last_memory_revision", 0.0),
                "last_memory_sync": snapshot.get("last_memory_sync", 0.0),
            },
            "observability": _memory_observability(snapshot, queue, lease, now),
        }
    )


@router.get("/memory/snapshot")
async def memory_snapshot(request: Request, key_pattern: str = "") -> JSONResponse:
    coordinator = _get_coordinator(request)
    if await coordinator.is_primary():
        return JSONResponse(await build_memory_snapshot(request, key_pattern=key_pattern))

    bridge = _get_node_bridge(request)
    if bridge.peer_urls:
        remote = await bridge.request_memory_snapshot(key_pattern=key_pattern)
        if remote.get("ok"):
            payload = dict(remote.get("snapshot", {}))
            payload["source"] = {
                "mode": "peer",
                "peer": remote.get("peer"),
                "node_id": coordinator.node_id,
            }
            return JSONResponse(payload)

    return JSONResponse(await build_memory_snapshot(request, key_pattern=key_pattern))


@router.get("/diagnostics")
async def node_diagnostics(request: Request, key_pattern: str = "") -> JSONResponse:
    coordinator = _get_coordinator(request)
    bridge = _get_node_bridge(request)
    memory = await build_memory_snapshot(request, key_pattern=key_pattern)
    cluster = await _peer_cluster_state(request)
    payload = {
        "ok": True,
        "node": coordinator.snapshot(),
        "bridge": {
            "base_url": bridge.base_url,
            "peer_urls": bridge.peer_urls,
        },
        "cluster": cluster,
        "memory": memory,
    }
    return JSONResponse(payload)
