import pytest
from unittest.mock import AsyncMock, patch

from src.tools.delete_memory import run as delete_memory_run


@pytest.mark.anyio
async def test_delete_memory_empty_key_returns_error():
    result = await delete_memory_run(key="")
    assert result == "[ERROR] key is required."


@pytest.mark.anyio
async def test_delete_memory_empty_key_after_strip_returns_error():
    result = await delete_memory_run(key="   ")
    assert result == "[ERROR] key is required."


@pytest.mark.anyio
async def test_delete_memory_delegates_to_save_memory():
    mock_save = AsyncMock(return_value="[OK] deleted key 'user:test' in MEMORY.md.")
    with patch("src.tools.save_memory.run", mock_save):
        result = await delete_memory_run(key="user:test")

    mock_save.assert_awaited_once_with(key="user:test", value="")
    assert result == "[OK] deleted key 'user:test' in MEMORY.md."


@pytest.mark.anyio
async def test_delete_memory_passes_extra_kwargs():
    mock_save = AsyncMock(return_value="[OK] deleted key 'user:x' in MEMORY.md.")
    with patch("src.tools.save_memory.run", mock_save):
        result = await delete_memory_run(
            key="user:x",
            _session_id="sess-1",
            _repos="fake",
        )

    mock_save.assert_awaited_once_with(
        key="user:x", value="", _session_id="sess-1", _repos="fake"
    )
    assert "[OK]" in result
