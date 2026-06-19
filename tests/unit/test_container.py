from src.llm.container import LLMContainer, get_container


def test_get_container_creates_a_fresh_instance_each_time():
    first = get_container()
    second = get_container()
    assert first is not second


def test_container_can_be_instantiated_directly():
    container = LLMContainer()
    assert container.get_circuit_breaker() is container.get_circuit_breaker()
    assert container.get_rate_limit_store() is container.get_rate_limit_store()
