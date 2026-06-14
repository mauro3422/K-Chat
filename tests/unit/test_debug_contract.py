import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

from src.api.debug_contract import DebugOpsDeps
from src.api.debug import save_debug_info, get_debug_info


@pytest.mark.anyio
async def test_debug_ops_deps_defaults_are_empty():
    deps = DebugOpsDeps()

    assert deps.debug_repo is None


@pytest.mark.anyio
async def test_debug_contract_allows_injected_repo():
    repo = MagicMock()
    repo.get_info = AsyncMock(return_value={})
    repo.save_info = AsyncMock()

    deps = DebugOpsDeps(debug_repo=repo)
    await save_debug_info("sess-1", {"model": "m"}, deps=deps)
    await get_debug_info("sess-1", deps=deps)

    repo.save_info.assert_called_once_with("sess-1", {"model": "m"})
    repo.get_info.assert_called_once_with("sess-1")
