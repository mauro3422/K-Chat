from src.memory.embeddings.service import (
    configure_model,
    reset_model,
)


class _DummyEmbeddingModel:
    pass


def test_configure_model_sets_explicit_instance():
    model = _DummyEmbeddingModel()
    configure_model(model)
    try:
        from src.memory.embeddings import service
        assert service._embedding_model is model
    finally:
        reset_model()


def test_reset_model_clears_cached_instance():
    model = _DummyEmbeddingModel()
    configure_model(model)
    reset_model()
    from src.memory.embeddings import service
    assert service._embedding_model is None
