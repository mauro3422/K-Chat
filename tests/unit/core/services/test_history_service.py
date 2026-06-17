import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.services.history_service import HistoryService


@pytest.mark.anyio
async def test_rebuild_calls_rebuild_history_with_repos():
    mock_repos = MagicMock()
    mock_repos.messages = AsyncMock()
    service = HistoryService(repos=mock_repos)

    with patch(
        "src.core.services.history_service.rebuild_history",
        new_callable=AsyncMock,
        return_value=[{"role": "system", "content": "sys"}],
    ) as mock_rebuild:
        result = await service.rebuild("sess-1", "model-x")

    mock_rebuild.assert_called_once_with("sess-1", "model-x", mock_repos.messages)
    assert result == [{"role": "system", "content": "sys"}]


@pytest.mark.anyio
async def test_rebuild_with_none_repos_gets_default_repos():
    service = HistoryService(repos=None)

    fake_repos = MagicMock()
    fake_repos.messages = AsyncMock()

    with patch(
        "src.core.services.history_service.rebuild_history",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_rebuild:
        with patch("src.core.services.history_service.get_repos", return_value=fake_repos):
            await service.rebuild("sess-1", "model-x")

    mock_rebuild.assert_called_once_with("sess-1", "model-x", fake_repos.messages)


@pytest.mark.anyio
async def test_get_system_prompt_calls_build_system_prompt():
    mock_builder = MagicMock(return_value={"role": "system", "content": "custom"})
    service = HistoryService(context_builder=mock_builder)
    result = service.get_system_prompt("gpt-4", tool_definitions={"t1": "v1"})

    mock_builder.assert_called_once_with("gpt-4", tool_definitions={"t1": "v1"})
    assert result == {"role": "system", "content": "custom"}


@pytest.mark.anyio
async def test_get_system_prompt_without_tool_defs():
    mock_builder = MagicMock(return_value={"role": "system", "content": "sys"})
    service = HistoryService(context_builder=mock_builder)
    result = service.get_system_prompt("gpt-4")

    mock_builder.assert_called_once_with("gpt-4", tool_definitions=None)
    assert result == {"role": "system", "content": "sys"}


@pytest.mark.anyio
async def test_compress_if_needed_calls_compress():
    service = HistoryService()
    compress_fn = AsyncMock()

    with patch(
        "src.core.services.history_service.should_compress",
        return_value=True,
    ):
        await service.compress_if_needed(
            [{"role": "user", "content": "a" * 5000}],
            "gpt-4",
            compress_fn=compress_fn,
        )

    compress_fn.assert_awaited_once()


@pytest.mark.anyio
async def test_compress_if_needed_skips_when_not_needed():
    service = HistoryService()
    compress_fn = AsyncMock()

    with patch(
        "src.core.services.history_service.should_compress",
        return_value=False,
    ):
        await service.compress_if_needed(
            [{"role": "user", "content": "hi"}],
            "gpt-4",
            compress_fn=compress_fn,
        )

    compress_fn.assert_not_called()


@pytest.mark.anyio
async def test_compress_if_needed_handles_exception_gracefully():
    service = HistoryService()
    compress_fn = AsyncMock(side_effect=Exception("boom"))

    with patch(
        "src.core.services.history_service.should_compress",
        return_value=True,
    ):
        await service.compress_if_needed(
            [{"role": "user", "content": "a" * 5000}],
            "gpt-4",
            compress_fn=compress_fn,
        )

    compress_fn.assert_awaited_once()
