from src.llm.container import LLMContainer, configure_container, get_container, reset_container


def test_configure_container_sets_explicit_instance():
    container = LLMContainer()
    configure_container(container)
    try:
        assert get_container() is container
    finally:
        reset_container()


def test_reset_container_restores_lazy_instance():
    container = LLMContainer()
    configure_container(container)
    reset_container()
    assert get_container() is not container
