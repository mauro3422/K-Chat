import json
import logging
from unittest.mock import patch, MagicMock, mock_open


def test_jsonl_handler_emit():
    from web.services import file_logger

    with patch("web.services.file_logger._ensure_dirs"):
        with patch("web.services.file_logger.SERVER_LOG_DIR", MagicMock()):
            with patch("builtins.open", mock_open()) as mock_file:
                handler = file_logger.JsonlHandler()
                record = logging.LogRecord(
                    name="test_module",
                    level=logging.INFO,
                    pathname="",
                    lineno=0,
                    msg="Test message",
                    args=(),
                    exc_info=None
                )

                handler.emit(record)

                assert mock_file().write.called
                written = mock_file().write.call_args[0][0]
                entry = json.loads(written.strip())
                assert entry["m"] == "test_module"
                assert entry["l"] == "I"
                assert entry["msg"] == "Test message"


def test_jsonl_handler_build_entry_with_data():
    from web.services import file_logger

    handler = file_logger.JsonlHandler()
    record = logging.LogRecord(
        name="test_module",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None
    )
    record.data = {"key": "value"}

    entry = handler._build_entry(record)

    assert entry["m"] == "test_module"
    assert entry["l"] == "W"
    assert entry["msg"] == "Test message"
    assert entry["d"] == {"key": "value"}


def test_jsonl_handler_build_entry_with_args():
    from web.services import file_logger

    handler = file_logger.JsonlHandler()
    record = logging.LogRecord(
        name="test_module",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Test %s %d",
        args=("arg1", 42),
        exc_info=None
    )

    entry = handler._build_entry(record)

    assert entry["m"] == "test_module"
    assert entry["l"] == "E"
    assert entry["msg"] == "Test arg1 42"
    assert entry["d"] == {"args": ("arg1", 42)}


def test_ensure_dirs():
    from web.services import file_logger

    with patch("web.services.file_logger.SERVER_LOG_DIR") as mock_server_dir:
        with patch("web.services.file_logger.CLIENT_LOG_DIR") as mock_client_dir:
            file_logger._ensure_dirs()

            mock_server_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
            mock_client_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_install_jsonl_handler():
    from web.services import file_logger

    with patch("web.services.file_logger.JsonlHandler") as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            result = file_logger.install_jsonl_handler("test_module")

            assert result == mock_handler
            mock_handler_class.assert_called_once_with("test_module")
            mock_logger.addHandler.assert_called_once_with(mock_handler)


def test_install_jsonl_handler_default_module():
    from web.services import file_logger

    with patch("web.services.file_logger.JsonlHandler") as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            result = file_logger.install_jsonl_handler()

            assert result == mock_handler
            mock_handler_class.assert_called_once_with("app")
            mock_logger.addHandler.assert_called_once_with(mock_handler)


def test_root_logger_has_add_handler():
    from web.services import file_logger
    assert hasattr(file_logger, "JsonlHandler")
    assert hasattr(file_logger, "install_jsonl_handler")
    assert hasattr(file_logger, "_ensure_dirs")
