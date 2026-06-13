from unittest.mock import MagicMock, patch

from src.core.history_contract import HistoryRebuildDeps
from src.core.history_rebuilder import rebuild_history


def test_history_rebuild_deps_defaults_are_empty():
    deps = HistoryRebuildDeps()

    assert deps.messages_repo is None


def test_rebuild_history_uses_injected_deps():
    repo = MagicMock()
    repo.get_session_messages.return_value = []

    with patch("src.core.history_rebuilder.build_system_prompt", return_value={"role": "system", "content": "sys"}):
        result = rebuild_history("sess-1", "model-x", deps=HistoryRebuildDeps(messages_repo=repo))

    repo.get_session_messages.assert_called_once_with("sess-1")
    assert result == [{"role": "system", "content": "sys"}]
