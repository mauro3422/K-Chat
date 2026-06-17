import pytest
import time

from src.tools._rate_limiter import _check_rate_limit, _call_counts, _RATE_MAX, _RATE_WINDOW, PER_TOOL_LIMITS


def _clean():
    _call_counts.clear()


@pytest.mark.anyio
async def test_rate_limit_empty_session_id():
    _clean()
    ok, msg = _check_rate_limit("")
    assert ok is True
    assert msg == ""


@pytest.mark.anyio
async def test_rate_limit_valid_session_normal_bucket():
    _clean()
    ok, msg = _check_rate_limit("sess1")
    assert ok is True
    assert msg == ""
    assert len(_call_counts["global"]["sess1"]) == 1


@pytest.mark.anyio
async def test_rate_limit_reached():
    _clean()
    now = time.time()
    bucket = _call_counts["global"]["sess2"]
    bucket[:] = [now - 0.1 * i for i in range(_RATE_MAX)]
    ok, msg = _check_rate_limit("sess2")
    assert ok is False
    assert "Rate limit reached" in msg


@pytest.mark.anyio
async def test_rate_limit_old_bucket_cleanup():
    _clean()
    old_time = time.time() - _RATE_WINDOW - 10
    _call_counts["global"]["sess3"] = [old_time, old_time, old_time]
    ok, msg = _check_rate_limit("sess3")
    assert ok is True
    assert len(_call_counts["global"]["sess3"]) == 1


@pytest.mark.anyio
async def test_rate_limit_with_tool_name():
    _clean()
    # save_memory has limit 10/30s
    tool_name = "save_memory"
    tool_max, _ = PER_TOOL_LIMITS[tool_name]
    now = time.time()
    bucket = _call_counts[tool_name]["sess4"]
    bucket[:] = [now - 0.1 * i for i in range(tool_max)]
    ok, msg = _check_rate_limit("sess4", tool_name=tool_name)
    assert ok is False
    assert f"Rate limit reached for '{tool_name}'" in msg


@pytest.mark.anyio
async def test_rate_limit_tool_still_allows_global():
    _clean()
    # Fill tool bucket but not global → should still be rejected
    tool_name = "save_memory"
    tool_max, _ = PER_TOOL_LIMITS[tool_name]
    now = time.time()
    _call_counts[tool_name]["sess5"] = [now - 0.1 * i for i in range(tool_max)]
    ok, msg = _check_rate_limit("sess5", tool_name=tool_name)
    assert ok is False
    assert f"Rate limit reached for '{tool_name}'" in msg


@pytest.mark.anyio
async def test_rate_limit_unknown_tool_falls_to_global():
    """Tools not in PER_TOOL_LIMITS should use global limit only."""
    _clean()
    for _ in range(5):
        ok, msg = _check_rate_limit("sess6", tool_name="unknown_tool")
        assert ok is True
    assert len(_call_counts["global"]["sess6"]) == 5
