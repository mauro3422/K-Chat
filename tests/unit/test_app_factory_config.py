from web import app_factory
from unittest.mock import patch


def test_reset_config_cache_clears_cached_config():
    app_factory._config = object()
    app_factory.reset_config_cache()
    assert app_factory._config is None


def test_reset_web_runtime_state_clears_web_owned_singletons():
    with (
        patch("web.services.file_logger.reset_log_dirs") as mock_log_dirs,
        patch("web.services.model_catalog.reset_model_cache") as mock_model_cache,
        patch("web.services.event_bus.reset_event_bus") as mock_event_bus,
        patch("web.app_factory.reset_config_cache") as mock_config_cache,
    ):
        app_factory.reset_web_runtime_state()

    mock_log_dirs.assert_called_once()
    mock_model_cache.assert_called_once()
    mock_event_bus.assert_called_once()
    mock_config_cache.assert_called_once()
