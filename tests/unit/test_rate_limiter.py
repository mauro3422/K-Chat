import time

from src.tools._rate_limiter import _check_rate_limit, _session_rate, _RATE_MAX, _RATE_WINDOW


def _clean():
    _session_rate.clear()


def test_rate_limit_empty_session_id():
    _clean()
    ok, msg = _check_rate_limit("")
    assert ok is True
    assert msg == ""


def test_rate_limit_valid_session_normal_bucket():
    _clean()
    ok, msg = _check_rate_limit("sess1")
    assert ok is True
    assert msg == ""
    assert len(_session_rate["sess1"]) == 1


def test_rate_limit_reached():
    _clean()
    now = time.time()
    bucket = _session_rate["sess2"]
    bucket[:] = [now - 0.1 * i for i in range(_RATE_MAX)]
    ok, msg = _check_rate_limit("sess2")
    assert ok is False
    assert "Rate limit reached" in msg


def test_rate_limit_old_bucket_cleanup():
    _clean()
    old_time = time.time() - _RATE_WINDOW - 10
    _session_rate["sess3"] = [old_time, old_time, old_time]
    ok, msg = _check_rate_limit("sess3")
    assert ok is True
    assert len(_session_rate["sess3"]) == 1
