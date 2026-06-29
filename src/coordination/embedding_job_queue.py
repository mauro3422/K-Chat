"""Persistent FIFO queue for deferred embedding jobs."""

from __future__ import annotations

import json
import os
import time
from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path


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
        )
        self._queue.append(request)
        self._persist()
        return request

    def snapshot(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._queue]

    def drain(self) -> list[EmbeddingJobRequest]:
        drained = list(self._queue)
        self._queue.clear()
        self._persist()
        return drained

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
                    )
                )
            except Exception:
                continue

    def _persist(self) -> None:
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._persistence_path.with_suffix(self._persistence_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self._persistence_path)


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

