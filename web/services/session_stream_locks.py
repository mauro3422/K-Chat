from __future__ import annotations

import asyncio


class SessionStreamLockManager:
    """Manage per-session stream locks for chat requests.

    The manager keeps one async lock per session_id and rejects concurrent
    streams for the same session while the active stream is still running.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    async def try_acquire(self, session_id: str) -> asyncio.Lock | None:
        """Acquire the lock for *session_id* if it is currently free."""
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock

        if lock.locked():
            return None

        await lock.acquire()
        return lock

    def release(self, session_id: str, lock: asyncio.Lock | None) -> None:
        """Release and drop the lock if it still belongs to *session_id*."""
        if lock is None:
            return

        current = self._locks.get(session_id)
        if current is not lock:
            return

        if lock.locked():
            lock.release()

        self._locks.pop(session_id, None)
