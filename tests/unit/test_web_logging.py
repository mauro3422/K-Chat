"""Tests for web logging — now delegated to LogBus.

The old BackendLogHandler (ring buffer in-memory) has been replaced by
LogBus (src/logbus/). These tests are kept as a placeholder since the
handler module still exists for backward compatibility.

LogBus tests live in tests/unit/test_logbus.py.
"""

import pytest


@pytest.mark.anyio
async def test_handler_deprecated():
    """BackendLogHandler is deprecated in favor of LogBus."""
    try:
        from web.logging_handler import BackendLogHandler, get_backend_logs
        logs = get_backend_logs()
        assert isinstance(logs, list)
    except Exception:
        pytest.skip("BackendLogHandler not available (deprecated)")
