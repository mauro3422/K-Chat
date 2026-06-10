import logging

from web.logging import BackendLogHandler, get_backend_logs


def _reset_buffer():
    """Reset the shared buffer for test isolation."""
    import web.logging as wl
    wl._backend_log_buffer.clear()


def test_handler_captures_records():
    """BackendLogHandler captures a log record and get_backend_logs returns it."""
    _reset_buffer()
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
    _reset_buffer()
    logger = logging.getLogger("kairos.test-copy")
    logger.setLevel(logging.DEBUG)

    logger.info("msg1")
    logs_a = get_backend_logs()
    logs_b = get_backend_logs()
    assert logs_a == logs_b
    assert logs_a is not logs_b


def test_ring_buffer_overflow():
    """When the buffer exceeds _max_backend_logs, oldest records are dropped."""
    _reset_buffer()
    import web.logging as wl
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
    """The module installs BackendLogHandler at import time."""
    kairos_logger = logging.getLogger("kairos")
    handler_types = [h for h in kairos_logger.handlers if isinstance(h, BackendLogHandler)]
    assert len(handler_types) >= 1, "BackendLogHandler should be installed at import time"
