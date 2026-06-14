import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock, patch

from src.api.debug import append_asr_telemetry
from src.api.debug_contract import DebugOpsDeps


@pytest.mark.anyio
async def test_append_asr_telemetry_appends_and_persists():
    repo = MagicMock()
    repo.get_info = AsyncMock(return_value={"asr_telemetry": [{"transport": "http"}], "model": "m1"})
    repo.save_info = AsyncMock()

    await append_asr_telemetry("sess-1", {"transport": "ws", "bytes": 123}, deps=DebugOpsDeps(debug_repo=repo))

    repo.get_info.assert_called_once_with("sess-1")
    repo.save_info.assert_called_once()
    saved_session, saved_data = repo.save_info.call_args.args
    assert saved_session == "sess-1"
    assert saved_data["asr_telemetry"] == [
        {"transport": "http"},
        {"transport": "ws", "bytes": 123},
    ]
