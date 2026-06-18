import asyncio
from concurrent.futures import ThreadPoolExecutor
import anyio

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
