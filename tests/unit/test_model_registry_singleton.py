from src.llm.model_registry import (
    ModelRegistry,
    configure_model_registry,
    get_model_registry,
    reset_model_registry,
)


def test_configure_model_registry_returns_explicit_registry():
    reg = ModelRegistry(config=None)
    configure_model_registry(reg)
    try:
        assert get_model_registry() is reg
    finally:
        reset_model_registry()


def test_reset_model_registry_restores_context_local_registry():
    reg = ModelRegistry(config=None)
    configure_model_registry(reg)
    reset_model_registry()
    new_reg = get_model_registry()
    assert new_reg is not reg
