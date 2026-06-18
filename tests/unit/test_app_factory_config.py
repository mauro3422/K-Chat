from web import app_factory


def test_reset_config_cache_clears_cached_config():
    app_factory._config = object()
    app_factory.reset_config_cache()
    assert app_factory._config is None
