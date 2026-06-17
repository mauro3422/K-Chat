from concurrent.futures import ThreadPoolExecutor
import asyncio

# Shared thread pool to prevent thread exhaustion from asyncio.to_thread
_thread_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="kairos_worker")


async def run_in_thread(fn, *args, **kwargs):
    """Run a blocking function in the shared thread pool.

    Drop-in replacement for asyncio.to_thread() with a capped worker pool
    instead of the default unbounded thread pool.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_thread_pool, lambda: fn(*args, **kwargs))
