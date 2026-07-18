import threading
import time
from collections import defaultdict

PER_TOOL_LIMITS: dict[str, tuple[int, int]] = {
    "save_memory": (10, 30),
    "recall_memories": (5, 30),
    "hydrate_memory_receipt": (10, 30),
    "memory_search": (10, 30),
    "manage_memory": (5, 30),
    "delete_memory": (10, 30),
    "search_entities": (15, 30),
    "explore_graph": (15, 30),
    "list_memories": (20, 30),
}

_call_counts: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
_rate_lock: threading.Lock = threading.Lock()
_RATE_MAX: int = 30
_RATE_WINDOW: float = 10.0
_RATE_CLEANUP_INTERVAL: int = 100  # Cleanup stale sessions every N calls
_cleanup_counter: int = 0


def _cleanup_stale_sessions() -> None:
    """Remove sessions that haven't made any calls in the last 300 seconds."""
    now = time.time()
    stale_cutoff = now - 300
    for tool_key in list(_call_counts.keys()):
        for session_key in list(_call_counts[tool_key].keys()):
            timestamps = _call_counts[tool_key][session_key]
            if not timestamps or max(timestamps) < stale_cutoff:
                del _call_counts[tool_key][session_key]
        if not _call_counts[tool_key]:
            del _call_counts[tool_key]


def _check_rate_limit(session_id: str, tool_name: str | None = None) -> tuple[bool, str]:
    if not session_id:
        return True, ""
    now = time.time()
    with _rate_lock:
        global _cleanup_counter
        _cleanup_counter += 1
        if _cleanup_counter >= _RATE_CLEANUP_INTERVAL:
            _cleanup_counter = 0
            _cleanup_stale_sessions()

        if tool_name and tool_name in PER_TOOL_LIMITS:
            tool_max, tool_window = PER_TOOL_LIMITS[tool_name]
            bucket = _call_counts[tool_name][session_id]
            bucket[:] = [t for t in bucket if now - t < tool_window]
            if len(bucket) >= tool_max:
                wait = round(tool_window - (now - bucket[0]))
                return False, f"[ERROR]: Rate limit reached for '{tool_name}'. Wait {wait}s before continuing."
            bucket.append(now)

        bucket = _call_counts["global"][session_id]
        bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
        if len(bucket) >= _RATE_MAX:
            wait = round(_RATE_WINDOW - (now - bucket[0]))
            return False, f"[ERROR]: Rate limit reached. Wait {wait}s before continuing."
        bucket.append(now)
    return True, ""
