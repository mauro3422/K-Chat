from src.memory.connection_pool import ConnectionPool
from src.memory.memory_pool import (
    configure_memory_pool,
    get_memory_pool,
    reset_memory_pool,
)


def test_configure_memory_pool_sets_explicit_pool():
    pool = ConnectionPool(max_connections=2)
    configure_memory_pool(pool)
    try:
        assert get_memory_pool() is pool
    finally:
        reset_memory_pool()


def test_reset_memory_pool_restores_fresh_pool():
    pool = ConnectionPool(max_connections=2)
    configure_memory_pool(pool)
    reset_memory_pool()
    assert get_memory_pool() is not pool
