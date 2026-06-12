from unittest.mock import patch, MagicMock

from src.background_tasks import auto_rename_session


def test_auto_rename_skips_when_already_named():
    mock_repo = MagicMock()
    mock_repo.check_should_rename.return_value = False
    with patch("src.api._repos._get_repo", return_value=mock_repo):
        with patch("src.background_tasks.llm_chat") as mock_chat:
            auto_rename_session("sess_1", "Hello", "model-x")
            mock_chat.assert_not_called()
            mock_repo.rename.assert_not_called()


def test_auto_rename_generates_and_saves_title():
    mock_response = MagicMock()
    mock_response.message.content = '"My Great Title"'
    mock_repo = MagicMock()
    mock_repo.check_should_rename.return_value = True

    with patch("src.api._repos._get_repo", return_value=mock_repo):
        with patch("src.background_tasks.llm_chat", return_value=mock_response) as mock_chat:
            auto_rename_session("sess_1", "This is my first message", "model-x")

            mock_chat.assert_called_once()
            assert mock_chat.call_args[0][1] == "model-x"
            mock_repo.rename.assert_called_once_with("sess_1", "My Great Title")


def test_auto_rename_skips_on_empty_title():
    mock_response = MagicMock()
    mock_response.message.content = "   "
    mock_repo = MagicMock()
    mock_repo.check_should_rename.return_value = True

    with patch("src.api._repos._get_repo", return_value=mock_repo):
        with patch("src.background_tasks.llm_chat", return_value=mock_response):
            auto_rename_session("sess_1", "Hello", "model-x")
            mock_repo.rename.assert_not_called()


def test_auto_rename_handles_llm_error():
    mock_repo = MagicMock()
    mock_repo.check_should_rename.return_value = True

    with patch("src.api._repos._get_repo", return_value=mock_repo):
        with patch("src.background_tasks.llm_chat", side_effect=Exception("API error")):
            auto_rename_session("sess_1", "Hello", "model-x")
            mock_repo.rename.assert_not_called()
