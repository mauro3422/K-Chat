from src.llm.rate_limit_state import (
    ModelRateLimitStore,
    configure_rate_limit_store,
    get_rate_limit_store,
    reset_rate_limit_store,
)


def test_configure_rate_limit_store_sets_explicit_instance():
    store = ModelRateLimitStore()
    configure_rate_limit_store(store)
    try:
        assert get_rate_limit_store() is store
    finally:
        reset_rate_limit_store()


def test_reset_rate_limit_store_restores_lazy_instance():
    store = ModelRateLimitStore()
    configure_rate_limit_store(store)
    reset_rate_limit_store()
    assert get_rate_limit_store() is not store
