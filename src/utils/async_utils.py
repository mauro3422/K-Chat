import asyncio
import inspect
import logging
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
import anyio

logger = logging.getLogger(__name__)

def _new_thread_pool() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=8, thread_name_prefix="kairos_worker")


# Shared thread pool to prevent thread exhaustion from asyncio.to_thread
_thread_pool = _new_thread_pool()


def configure_thread_pool(pool: ThreadPoolExecutor | None) -> None:
    """Set the thread pool used by run_in_thread."""
    global _thread_pool
    _thread_pool = pool or _new_thread_pool()


def reset_thread_pool() -> None:
    """Restore the default shared thread pool."""
    shutdown_thread_pool()


def shutdown_thread_pool() -> None:
    """Shut down the active thread pool safely."""
    global _thread_pool
    pool = _thread_pool
    _thread_pool = _new_thread_pool()
    pool.shutdown(wait=False, cancel_futures=True)


async def run_in_thread(fn, *args, **kwargs):
    """Run a blocking function in the shared thread pool.

    Drop-in replacement for asyncio.to_thread() with a capped worker pool
    instead of the default unbounded thread pool.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))
    return await loop.run_in_executor(_thread_pool, lambda: fn(*args, **kwargs))


async def sleep(delay: float) -> None:
    """Sleep with asyncio first, falling back to anyio when no asyncio loop is running."""
    try:
        await asyncio.sleep(delay)
    except RuntimeError:
        await anyio.sleep(delay)


def schedule_background_awaitable(awaitable, *, label: str = "background task") -> None:
    """Run an awaitable in the current loop when possible, otherwise on a daemon thread.

    This keeps fire-and-forget work non-blocking without binding the caller to a
    specific async backend.
    """
    if not inspect.isawaitable(awaitable):
        return

    async def _consume() -> None:
        try:
            await awaitable
        except Exception:
            logger.exception("Background %s failed", label)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        threading.Thread(target=lambda: asyncio.run(_consume()), daemon=True).start()
        return

    task = loop.create_task(_consume())

    def _log_task_failure(t: asyncio.Task) -> None:
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Background %s callback failed", label)
            return
        if exc is not None:
            logger.error("Background %s failed: %s", label, exc, exc_info=(type(exc), exc, exc.__traceback__))

    task.add_done_callback(_log_task_failure)


def run_awaitable_sync(awaitable, *, label: str = "awaitable") -> object:
    """Run an awaitable from synchronous code.

    If no event loop is running, use asyncio.run directly. If we are already
    inside an event loop, run the awaitable on a daemon thread and wait for the
    result there so callers do not need to care about the active backend.
    """
    if not inspect.isawaitable(awaitable):
        return awaitable

    async def _consume() -> object:
        return await awaitable

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_consume())

    result: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def _worker() -> None:
        try:
            result.put((True, asyncio.run(_consume())))
        except Exception as exc:
            result.put((False, exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    ok, payload = result.get()
    if ok:
        return payload
    if isinstance(payload, BaseException):
        raise payload
    raise RuntimeError(str(payload))
