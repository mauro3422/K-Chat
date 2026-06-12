import logging

import pytest

from web.logging_handler import BackendLogHandler, get_backend_logs


@pytest.fixture(autouse=True)
def _isolate_logging():
    """Reset the shared log buffer and restore the global logging threshold.

    Some tests call ``logging.disable(logging.CRITICAL)`` which sets
    ``logging.root.manager.disable`` to CRITICAL, globally suppressing
    all records below that level.  That persists across tests because
    nobody restores it, so INFO messages never reach the
    ``BackendLogHandler``.  We snapshot and restore the disable threshold
    here to guarantee every test starts with a clean logging state.
    """
    from web.logging_handler import _reset_buffer
    saved_disable = logging.root.manager.disable
    logging.root.manager.disable = 0
    _reset_buffer()
    yield
    _reset_buffer()
    logging.root.manager.disable = saved_disable


def test_handler_captures_records():
    """BackendLogHandler captures a log record and get_backend_logs returns it."""
    logger = logging.getLogger("kairos.test-capture")
    logger.setLevel(logging.DEBUG)

    logger.info("hello world")
    logs = get_backend_logs()
    assert len(logs) >= 1
    entry = next((line for line in logs if line["logger"] == "kairos.test-capture"), None)
    assert entry is not None
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "kairos.test-capture"
    assert "ts" in entry


def test_get_backend_logs_returns_copy():
    """get_backend_logs returns a copy, not the original mutable list."""
    logger = logging.getLogger("kairos.test-copy")
    logger.setLevel(logging.DEBUG)

    logger.info("msg1")
    logs_a = get_backend_logs()
    logs_b = get_backend_logs()
    assert logs_a == logs_b
    assert logs_a is not logs_b


def test_ring_buffer_overflow():
    """When the buffer exceeds _max_backend_logs, oldest records are dropped."""
    import web.logging_handler as wl
    original_max = wl._max_backend_logs
    wl._max_backend_logs = 5

    logger = logging.getLogger("kairos.test-ring")
    logger.setLevel(logging.DEBUG)

    for i in range(10):
        logger.info("record-%d", i)

    logs = get_backend_logs()
    # The kairos handler (installed at import time) captured all 10 records
    # with max=5, only the last 5 should remain
    # Filter to just our test-ring records to avoid interference from other tests
    test_logs = [line for line in logs if line["logger"] == "kairos.test-ring"]
    assert len(test_logs) == 5, f"Expected 5 test-ring logs, got {len(test_logs)} among {len(logs)} total"
    assert test_logs[0]["message"] == "record-5"
    assert test_logs[-1]["message"] == "record-9"

    wl._max_backend_logs = original_max


def test_handler_installed_by_default(caplog):
    """The module installs BackendLogHandler at import time on root logger."""
    root_logger = logging.root
    handler_types = [h for h in root_logger.handlers if isinstance(h, BackendLogHandler)]
    assert len(handler_types) >= 1, "BackendLogHandler should be installed on root logger at import time"
