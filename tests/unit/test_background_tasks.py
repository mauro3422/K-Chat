import pytest
from unittest.mock import MagicMock, AsyncMock

from src.background_tasks import auto_rename_session


@pytest.mark.anyio
async def test_auto_rename_skips_when_already_named():
    mock_repo = MagicMock()
    mock_repo.check_should_rename = AsyncMock(return_value=False)
    mock_chat = AsyncMock()
    title = await auto_rename_session("sess_1", "Hello", "model-x", chat_fn=mock_chat, session_repo=mock_repo)
    assert title is None
    mock_chat.assert_not_called()
    mock_repo.rename.assert_not_called()


@pytest.mark.anyio
async def test_auto_rename_generates_and_saves_title():
    mock_response = MagicMock()
    mock_response.message.content = '"My Great Title"'
    mock_repo = MagicMock()
    mock_repo.check_should_rename = AsyncMock(return_value=True)
    mock_repo.rename = AsyncMock()

    mock_chat = AsyncMock(return_value=mock_response)
    title = await auto_rename_session("sess_1", "This is my first message", "model-x", chat_fn=mock_chat, session_repo=mock_repo)

    mock_chat.assert_called_once()
    assert mock_chat.call_args[0][1] == "model-x"
    mock_repo.rename.assert_called_once_with("sess_1", "My Great Title")
    assert title == "My Great Title"


@pytest.mark.anyio
async def test_auto_rename_skips_on_empty_title():
    mock_response = MagicMock()
    mock_response.message.content = "   "
    mock_repo = MagicMock()
    mock_repo.check_should_rename = AsyncMock(return_value=True)

    mock_chat = AsyncMock(return_value=mock_response)
    await auto_rename_session("sess_1", "Hello", "model-x", chat_fn=mock_chat, session_repo=mock_repo)
    mock_repo.rename.assert_not_called()


@pytest.mark.anyio
async def test_auto_rename_handles_llm_error():
    mock_repo = MagicMock()
    mock_repo.check_should_rename = AsyncMock(return_value=True)

    mock_chat = AsyncMock(side_effect=Exception("API error"))
    await auto_rename_session("sess_1", "Hello", "model-x", chat_fn=mock_chat, session_repo=mock_repo)
    mock_repo.rename.assert_not_called()
