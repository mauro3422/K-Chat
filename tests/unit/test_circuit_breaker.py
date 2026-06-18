from src.llm.circuit_breaker import CircuitBreaker, configure_breaker, get_breaker, reset_breaker


def test_configure_breaker_sets_explicit_instance():
    breaker = CircuitBreaker()
    configure_breaker(breaker)
    try:
        assert get_breaker() is breaker
    finally:
        reset_breaker()


def test_reset_breaker_restores_lazy_instance():
    breaker = CircuitBreaker()
    configure_breaker(breaker)
    reset_breaker()
    assert get_breaker() is not breaker
