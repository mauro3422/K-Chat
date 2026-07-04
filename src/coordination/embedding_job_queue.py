"""Persistent FIFO queue for deferred embedding jobs."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmbeddingJobRequest:
    source: str
    source_key: str
    item_idx: int
    text: str
    content_hash: str
    requested_at: float
    source_node: str = ""
    reason: str = "primary_unavailable"
    status: str = "pending"
    attempts: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(asdict(self))


class EmbeddingJobQueue:
    """Simple JSON-backed queue for remote embedding work."""

    def __init__(self, *, persistence_path: str | None = None, config: Any | None = None) -> None:
        self._queue: deque[EmbeddingJobRequest] = deque()
        self._persistence_path = Path(
            persistence_path
            or os.environ.get("KAIROS_EMBEDDING_JOB_QUEUE_PATH")
            or f"{resolve_memory_db_path(config)}.embedding-queue.json"
        )
        self._load()

    def enqueue(
        self,
        *,
        source: str,
        source_key: str,
        item_idx: int,
        text: str,
        content_hash: str = "",
        source_node: str = "",
        reason: str = "primary_unavailable",
    ) -> EmbeddingJobRequest:
        request = EmbeddingJobRequest(
            source=source.strip() or "session",
            source_key=source_key.strip(),
            item_idx=int(item_idx),
            text=text,
            content_hash=content_hash.strip(),
            requested_at=time.time(),
            source_node=source_node.strip(),
            reason=reason,
            status="pending",
            attempts=0,
            last_error="",
        )
        self._queue.append(request)
        self._persist()
        return request

    def snapshot(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._queue]

    def drain(self) -> list[EmbeddingJobRequest]:
        drained: list[EmbeddingJobRequest] = []
        remaining: deque[EmbeddingJobRequest] = deque()
        for item in self._queue:
            if item.status in {"pending", "retryable"}:
                drained.append(item)
            else:
                remaining.append(item)
        self._queue = remaining
        self._persist()
        return drained

    def mark_retryable(self, item: EmbeddingJobRequest, *, error: str) -> EmbeddingJobRequest:
        retried = EmbeddingJobRequest(
            source=item.source,
            source_key=item.source_key,
            item_idx=item.item_idx,
            text=item.text,
            content_hash=item.content_hash,
            requested_at=item.requested_at,
            source_node=item.source_node,
            reason=item.reason,
            status="retryable",
            attempts=item.attempts + 1,
            last_error=error,
        )
        self._queue.append(retried)
        self._persist()
        return retried

    def mark_failed(self, item: EmbeddingJobRequest, *, error: str) -> EmbeddingJobRequest:
        failed = EmbeddingJobRequest(
            source=item.source,
            source_key=item.source_key,
            item_idx=item.item_idx,
            text=item.text,
            content_hash=item.content_hash,
            requested_at=item.requested_at,
            source_node=item.source_node,
            reason=item.reason,
            status="failed",
            attempts=item.attempts + 1,
            last_error=error,
        )
        self._queue.append(failed)
        self._persist()
        return failed

    def __len__(self) -> int:
        return len(self._queue)

    @property
    def persistence_path(self) -> str:
        return str(self._persistence_path)

    def _load(self) -> None:
        if not self._persistence_path.exists():
            return
        try:
            raw = json.loads(self._persistence_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load embedding job queue from %s — starting fresh", self._persistence_path)
            return
        items = raw if isinstance(raw, list) else raw.get("items", []) if isinstance(raw, dict) else []
        for item in items:
            try:
                self._queue.append(
                    EmbeddingJobRequest(
                        source=str(item.get("source", "session")).strip() or "session",
                        source_key=str(item.get("source_key", "")).strip(),
                        item_idx=int(item.get("item_idx", 0)),
                        text=str(item.get("text", "")),
                        content_hash=str(item.get("content_hash", "")).strip(),
                        requested_at=float(item.get("requested_at", time.time())),
                        source_node=str(item.get("source_node", "")).strip(),
                        reason=str(item.get("reason", "primary_unavailable")),
                        status=str(item.get("status", "pending") or "pending"),
                        attempts=int(item.get("attempts", 0) or 0),
                        last_error=str(item.get("last_error", "")),
                    )
                )
            except Exception:
                logger.warning("Skipping corrupt item in embedding job queue: %s", item.get("source_key", "?"))
                continue

    def _persist(self) -> None:
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._persistence_path.with_suffix(self._persistence_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.replace(tmp_path, self._persistence_path)
        except OSError as e:
            logger.error("Failed to persist embedding job queue (disk full?): %s", e)


_current_queue: ContextVar[EmbeddingJobQueue | None] = ContextVar("kairos_embedding_job_queue", default=None)


def configure_embedding_job_queue(queue: EmbeddingJobQueue | None) -> None:
    _current_queue.set(queue)


def reset_embedding_job_queue() -> None:
    _current_queue.set(None)


def get_embedding_job_queue(config: Any | None = None) -> EmbeddingJobQueue:
    queue = _current_queue.get()
    if queue is None:
        queue = EmbeddingJobQueue(config=config)
        _current_queue.set(queue)
    return queue


async def replay_pending_embedding_jobs(
    queue: EmbeddingJobQueue,
    deliver_request,
) -> list[dict[str, Any]]:
    pending = queue.drain()
    if not pending:
        return []

    applied: list[dict[str, Any]] = []
    for item in pending:
        try:
            result = await deliver_request(item)
        except Exception as exc:
            queue.mark_retryable(item, error=str(exc))
            continue

        if isinstance(result, dict) and bool(result.get("ok")) and not bool(result.get("queued", False)):
            applied.append({"source_key": item.source_key, "item_idx": item.item_idx, "result": "replayed"})
        else:
            error = str(result.get("error", "not accepted")) if isinstance(result, dict) else "not accepted"
            queue.mark_retryable(item, error=error)

    return applied
