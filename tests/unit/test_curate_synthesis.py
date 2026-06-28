from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.memory.curator import curate


@pytest.mark.anyio
async def test_curate_all_passes_sessions_db_to_daily_synthesis():
    save_memory = AsyncMock(return_value="[OK] saved")
    llm_call = AsyncMock(return_value="NO_NEW_INFO")
    synth = AsyncMock(return_value="memory/synthesis/2026/06/27.md")

    with (
        patch("src.memory.curator.curate._get_sessions_db_path", return_value="sessions.db"),
        patch("src.memory.curator.curate._get_memory_db_path", return_value="memory.db"),
        patch("src.memory.vectorize_sessions.vectorize_all_sessions", new=AsyncMock(return_value={})),
        patch("src.memory.repos.get_repos", return_value=SimpleNamespace()),
        patch("src.memory.curator.curate.curate_clusters", new=AsyncMock(return_value=[])),
        patch("src.memory.curator.curate.curate_sessions", new=AsyncMock(return_value=[])),
        patch("src.memory.synthesis.daily.generate_daily_synthesis", new=synth),
    ):
        result = await curate.curate_all(
            dry=False,
            save_memory_fn=save_memory,
            llm_call_fn=llm_call,
            run_gardener=False,
            run_tracer=False,
        )

    synth.assert_awaited_once_with(db_path="sessions.db")
    assert result["synthesis_path"] == "memory/synthesis/2026/06/27.md"
