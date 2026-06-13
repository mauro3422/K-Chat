from unittest.mock import MagicMock

from src.api.debug_contract import DebugOpsDeps
from src.api.debug import save_debug_info, get_debug_info


def test_debug_ops_deps_defaults_are_empty():
    deps = DebugOpsDeps()

    assert deps.debug_repo is None


def test_debug_contract_allows_injected_repo():
    repo = MagicMock()
    repo.get_info.return_value = {}

    deps = DebugOpsDeps(debug_repo=repo)
    save_debug_info("sess-1", {"model": "m"}, deps=deps)
    get_debug_info("sess-1", deps=deps)

    repo.save_info.assert_called_once_with("sess-1", {"model": "m"})
    repo.get_info.assert_called_once_with("sess-1")
