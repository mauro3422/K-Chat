"""In-memory queue for deferred memory write requests."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MemoryWriteRequest:
    key: str
    value: str
    requested_at: float
    source_node: str = ""
    reason: str = "permission_pending"

    def to_dict(self) -> dict[str, Any]:
        return dict(asdict(self))


class MemoryWriteQueue:
    """Simple FIFO queue for pending memory write requests."""

    def __init__(self, *, persistence_path: str | None = None, config: Any | None = None) -> None:
        self._queue: deque[MemoryWriteRequest] = deque()
        self._persistence_path = Path(
            persistence_path or os.environ.get("KAIROS_MEMORY_WRITE_QUEUE_PATH") or f"{resolve_memory_db_path(config)}.write-queue.json"
        )
        self._load()

    def enqueue(self, key: str, value: str, *, source_node: str = "", reason: str = "permission_pending") -> MemoryWriteRequest:
        request = MemoryWriteRequest(
            key=key.strip(),
            value=value,
            requested_at=time.time(),
            source_node=source_node.strip(),
            reason=reason,
        )
        self._queue.append(request)
        self._persist()
        return request

    def snapshot(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._queue]

    def drain(self) -> list[MemoryWriteRequest]:
        drained: list[MemoryWriteRequest] = list(self._queue)
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
            logger.exception("Failed to load memory write queue from %s — starting fresh", self._persistence_path)
            return
        items = raw if isinstance(raw, list) else raw.get("items", []) if isinstance(raw, dict) else []
        for item in items:
            try:
                self._queue.append(
                    MemoryWriteRequest(
                        key=str(item.get("key", "")).strip(),
                        value=str(item.get("value", "")),
                        requested_at=float(item.get("requested_at", time.time())),
                        source_node=str(item.get("source_node", "")).strip(),
                        reason=str(item.get("reason", "permission_pending")),
                    )
                )
            except Exception:
                logger.warning("Skipping corrupt item in write queue: %s", item.get("key", "?"))
                continue

    def _persist(self) -> None:
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._persistence_path.with_suffix(self._persistence_path.suffix + ".tmp")
        payload = [item.to_dict() for item in self._queue]
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.replace(tmp_path, self._persistence_path)
        except OSError as e:
            logger.error("Failed to persist write queue (disk full?): %s", e)


_current_queue: ContextVar[MemoryWriteQueue | None] = ContextVar("kairos_memory_write_queue", default=None)


def configure_memory_write_queue(queue: MemoryWriteQueue | None) -> None:
    _current_queue.set(queue)


def reset_memory_write_queue() -> None:
    _current_queue.set(None)


def get_memory_write_queue(config: Any | None = None) -> MemoryWriteQueue:
    queue = _current_queue.get()
    if queue is None:
        queue = MemoryWriteQueue(config=config)
        _current_queue.set(queue)
    return queue


async def apply_pending_memory_writes(
    queue: MemoryWriteQueue,
    save_memory_run,
    *,
    repos: Any | None = None,
) -> list[dict[str, str]]:
    pending = queue.drain()
    if not pending:
        return []

    results: list[dict[str, str]] = []
    for item in pending:
        result = await save_memory_run(
            key=item.key,
            value=item.value,
            _repos=repos,
            _force_local_write=True,
        )
        results.append({"key": item.key, "result": result})
    return results


async def replay_pending_memory_writes(
    queue: MemoryWriteQueue,
    deliver_request,
) -> list[dict[str, str]]:
    """Try to deliver queued writes to a live primary and keep failures queued."""
    pending = queue.drain()
    if not pending:
        return []

    remaining: list[MemoryWriteRequest] = []
    applied: list[dict[str, str]] = []

    for item in pending:
        try:
            result = await deliver_request(item)
        except Exception:
            remaining.append(item)
            continue

        ok = False
        if isinstance(result, dict):
            ok = bool(result.get("ok")) and bool(result.get("granted", False))
        else:
            ok = bool(result)

        if ok:
            applied.append({"key": item.key, "result": "replayed"})
        else:
            remaining.append(item)

    if remaining:
        queue._queue.extend(remaining)
        queue._persist()

    return applied
