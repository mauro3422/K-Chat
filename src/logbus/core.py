"""Core LogBus: async queue + consumer + writers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.logbus.models import LogEvent

logger = logging.getLogger(__name__)


class BaseWriter:
    """Abstract base for LogBus writers."""

    async def write(self, events: list[LogEvent]) -> None:
        raise NotImplementedError

    async def flush(self) -> None:
        pass


class LogBus:
    """Unified async logging bus.
    
    Non-blocking emit() → asyncio.Queue → background consumer → writers.
    """

    MAX_QUEUE = 2000
    BATCH_SIZE = 50
    FLUSH_INTERVAL = 2.0  # seconds

    def __init__(self) -> None:
        self._queue: asyncio.Queue[LogEvent] = asyncio.Queue(maxsize=self.MAX_QUEUE)
        self._writers: list[BaseWriter] = []
        self._consumer_task: asyncio.Task[Any] | None = None
        self._started = False

    def add_writer(self, writer: BaseWriter) -> None:
        self._writers.append(writer)

    def emit(self, event: LogEvent) -> None:
        """Non-blocking emit. Drops event if queue is full."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("LogBus queue full, dropping event: %s/%s", event.module, event.msg[:60])

    async def start(self) -> None:
        """Start the background consumer task."""
        if self._started:
            return
        self._started = True
        self._consumer_task = asyncio.create_task(self._consumer_loop())
        logger.info("LogBus started with %d writer(s)", len(self._writers))

    async def stop(self) -> None:
        """Stop the consumer and flush remaining events."""
        if not self._started:
            return
        self._started = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        # Flush what's left
        remaining: list[LogEvent] = []
        while not self._queue.empty():
            try:
                remaining.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if remaining:
            await self._write_all(remaining)
        for w in self._writers:
            await w.flush()
        logger.info("LogBus stopped, %d events flushed", len(remaining))

    async def _consumer_loop(self) -> None:
        """Background loop: batch-read queue and write."""
        batch: list[LogEvent] = []
        while self._started:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=self.FLUSH_INTERVAL
                )
                batch.append(event)
                if len(batch) >= self.BATCH_SIZE:
                    await self._write_all(batch)
                    batch = []
            except asyncio.TimeoutError:
                if batch:
                    await self._write_all(batch)
                    batch = []
            except asyncio.CancelledError:
                if batch:
                    await self._write_all(batch)
                raise

    async def _write_all(self, events: list[LogEvent]) -> None:
        for w in self._writers:
            try:
                await w.write(events)
            except Exception:
                logger.exception("LogBus writer %s failed", type(w).__name__)
