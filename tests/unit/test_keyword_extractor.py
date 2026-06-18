from src.memory.keywords.extractor import (
    TfidfExtractor,
    configure_global_extractor,
    extract_keywords,
    reset_global_extractor,
)


def test_configure_global_extractor_sets_explicit_instance():
    extractor = TfidfExtractor()
    configure_global_extractor(extractor)
    try:
        assert extract_keywords("hola mundo", top_k=2)
    finally:
        reset_global_extractor()


def test_reset_global_extractor_restores_seeded_behavior():
    extractor = TfidfExtractor()
    configure_global_extractor(extractor)
    reset_global_extractor()
    result = extract_keywords("hola mundo", top_k=2)
    assert result
