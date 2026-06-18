from pathlib import Path

from unittest.mock import MagicMock

from web.services.file_logger import configure_log_dirs, get_client_log_dir, get_server_log_dir, reset_log_dirs


def test_configure_log_dirs_sets_explicit_paths():
    server = Path("/tmp/server_logs")
    client = Path("/tmp/client_logs")
    configure_log_dirs(server, client)
    try:
        assert get_server_log_dir() == server
        assert get_client_log_dir() == client
    finally:
        reset_log_dirs()


def test_reset_log_dirs_restores_lazy_paths():
    server = Path("/tmp/server_logs")
    client = Path("/tmp/client_logs")
    configure_log_dirs(server, client)
    reset_log_dirs()
    assert get_server_log_dir() != server
    assert get_client_log_dir() != client


def test_getters_accept_explicit_config():
    config = MagicMock()
    config.kairos_log_dir = "/tmp/explicit_logs"
    reset_log_dirs()
    assert get_server_log_dir(config=config) == Path("/tmp/explicit_logs/server")
    assert get_client_log_dir(config=config) == Path("/tmp/explicit_logs/client")
