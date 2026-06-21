from src.memory.connection_pool import (
    ConnectionPool,
    configure_connection_pool,
    get_pool,
    get_conn,
    reset_connection_pool,
)


def test_configure_connection_pool_sets_explicit_pool():
    pool = ConnectionPool(max_connections=1)
    configure_connection_pool(pool)
    try:
        assert get_pool() is pool
    finally:
        reset_connection_pool()


def test_reset_connection_pool_restores_fresh_pool():
    pool = ConnectionPool(max_connections=1)
    configure_connection_pool(pool)
    reset_connection_pool()
    assert get_pool() is not pool
