from src.context.runtime import build_context_snapshot, invalidate_context_cache, reset_context_cache


def test_reset_context_cache_aliases_invalidate():
    invalidate_context_cache()
    result1 = build_context_snapshot(force=True)
    reset_context_cache()
    result2 = build_context_snapshot(force=True)
    assert result1.tools_md == result2.tools_md
