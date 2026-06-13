import threading
import time
from collections import defaultdict

_session_rate: dict[str, list[float]] = defaultdict(list)
_rate_lock: threading.Lock = threading.Lock()
_RATE_MAX: int = 30
_RATE_WINDOW: float = 10.0


def _check_rate_limit(session_id: str) -> tuple[bool, str]:
    if not session_id:
        return True, ""
    now = time.time()
    with _rate_lock:
        bucket = _session_rate[session_id]
        bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
        if len(bucket) >= _RATE_MAX:
            wait = round(_RATE_WINDOW - (now - bucket[0]))
            return False, f"[ERROR]: Rate limit reached. Wait {wait}s before continuing."
        bucket.append(now)
    return True, ""
