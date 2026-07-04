from unittest.mock import patch, MagicMock, ANY

import pytest

from src.llm.failover import _mark_and_refresh, _dynamic_switch_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rate_limit_error(msg: str = "429 rate limit exceeded") -> Exception:
    """Create a rate-limit-like exception without openai dependency."""
    exc = Exception(msg)
    exc.status_code = 429
    return exc


def _make_generic_error(msg: str = "server error") -> Exception:
    return Exception(msg)


# ---------------------------------------------------------------------------
# Existing tests — adapted for new breaker/failover logic
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@patch("src.llm.model_state.mark_model_failed")
@patch("src.llm.model_state._switch_model")
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_marks_model_as_failed_and_refreshes_verified_list(
    mock_get_verified_models, mock_switch_model, mock_mark_model_failed
):
    mock_get_verified_models.return_value = ["model1", "model2"]
    mock_switch_model.return_value = "model2"

    result = _mark_and_refresh("model1")

    mock_mark_model_failed.assert_called_once_with("model1")
    mock_switch_model.assert_called_once_with("model1")
    assert result == "model2"


@pytest.mark.anyio
@patch("src.llm.model_state.mark_model_failed")
@patch("src.llm.model_state._switch_model")
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_handles_refresh_failure_gracefully(
    mock_get_verified_models, mock_switch_model, mock_mark_model_failed
):
    mock_get_verified_models.side_effect = Exception("Refresh failed")
    mock_switch_model.return_value = "model2"

    result = _mark_and_refresh("model1")

    mock_mark_model_failed.assert_called_once_with("model1")
    mock_switch_model.assert_called_once_with("model1")
    assert result == "model2"


@pytest.mark.anyio
@patch("src.llm.model_state.mark_model_failed")
@patch("src.llm.model_state._switch_model")
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_falls_back_to_same_model_when_all_failed(
    mock_get_verified_models, mock_switch_model, mock_mark_model_failed
):
    mock_get_verified_models.return_value = ["model1", "model2"]
    mock_switch_model.side_effect = RuntimeError("All models have failed")
    breaker = MagicMock()
    breaker.is_available.return_value = True
    rate_store = MagicMock()
    rate_store.is_rate_limited.return_value = False

    result = _mark_and_refresh(
        "model1",
        breaker=breaker,
        rate_store=rate_store,
    )

    mock_mark_model_failed.assert_called_once_with("model1")
    mock_switch_model.assert_called_once_with("model1")
    assert result == "model1"


# ---------------------------------------------------------------------------
# NEW: Breaker + rate limit tests (Fix 1 — agent 1 findings)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_rate_limited_does_not_record_breaker(
    mock_get_verified_models,
):
    """Rate-limit errors must NOT increment circuit breaker failure count."""
    mock_get_verified_models.return_value = ["model-a", "model-b"]
    breaker = MagicMock()
    rate_store = MagicMock()
    rate_store.is_rate_limited.return_value = False
    rate_store.is_unavailable.return_value = False

    error = _make_rate_limit_error()
    result = _mark_and_refresh(
        "model-a", error=error, refresh=False,
        breaker=breaker, rate_store=rate_store,
    )

    # Breaker.record_failure must NOT be called for rate limit errors
    breaker.record_failure.assert_not_called()
    # But it should still record rate limit in the rate store
    rate_store.mark_rate_limited.assert_called_once_with("model-a", retry_after=ANY, detail=ANY)


@pytest.mark.anyio
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_rate_limited_does_not_mark_model_failed(
    mock_get_verified_models,
):
    """Rate-limit errors must NOT call mark_model_failed."""
    mock_get_verified_models.return_value = ["model-a", "model-b"]
    breaker = MagicMock()
    rate_store = MagicMock()
    rate_store.is_rate_limited.return_value = False
    rate_store.is_unavailable.return_value = False

    with patch("src.llm.model_state.mark_model_failed") as mock_mark:
        error = _make_rate_limit_error()
        _mark_and_refresh(
            "model-a", error=error, refresh=False,
            breaker=breaker, rate_store=rate_store,
        )
        mock_mark.assert_not_called()


@pytest.mark.anyio
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_generic_error_does_record_breaker(
    mock_get_verified_models,
):
    """Generic (non-rate-limit) errors SHOULD record breaker failure."""
    mock_get_verified_models.return_value = ["model-a"]
    breaker = MagicMock()
    rate_store = MagicMock()
    rate_store.is_rate_limited.return_value = False
    rate_store.is_unavailable.return_value = False

    error = _make_generic_error("Something went wrong")
    with patch("src.llm.model_state._switch_model", return_value="model-b"):
        with patch("src.llm.model_state.mark_model_failed"):
            _mark_and_refresh(
                "model-a", error=error, refresh=False,
                breaker=breaker, rate_store=rate_store,
            )
    breaker.record_failure.assert_called_once_with("model-a")


# ---------------------------------------------------------------------------
# NEW: Dynamic switch tests (Fix 3 — agent 3 findings)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_dynamic_switch_model_selects_preferred_free_fallback():
    """When primary is rate-limited, prefer deepseek-v4-flash-free from preferred."""
    registry = MagicMock()
    registry.get_verified_models.return_value = [
        "deepseek-v4-flash", "deepseek-v4-flash-free",
    ]
    registry.get_free_candidates.return_value = ["deepseek-v4-flash-free"]
    registry.get_all_models.return_value = [
        "deepseek-v4-flash", "deepseek-v4-flash-free",
    ]

    rate_store = MagicMock()
    rate_store.is_unavailable.return_value = False
    rate_store.is_rate_limited.return_value = False

    result = _dynamic_switch_model(
        "deepseek-v4-flash", registry=registry, rate_store=rate_store,
    )
    assert result == "deepseek-v4-flash-free"


@pytest.mark.anyio
async def test_dynamic_switch_model_skips_rate_limited_free_model():
    """When both primary and free model are rate-limited, return None."""
    registry = MagicMock()
    registry.get_verified_models.return_value = [
        "deepseek-v4-flash", "deepseek-v4-flash-free",
    ]
    registry.get_free_candidates.return_value = ["deepseek-v4-flash-free"]
    registry.get_all_models.return_value = [
        "deepseek-v4-flash", "deepseek-v4-flash-free",
    ]

    rate_store = MagicMock()
    rate_store.is_unavailable.return_value = False

    def is_rate_limited_side_effect(model: str) -> bool:
        return model.startswith("deepseek")  # both models rate-limited

    rate_store.is_rate_limited.side_effect = is_rate_limited_side_effect

    result = _dynamic_switch_model(
        "deepseek-v4-flash", registry=registry, rate_store=rate_store,
    )
    assert result is None


@pytest.mark.anyio
async def test_dynamic_switch_model_returns_none_when_no_candidates():
    """When registry has no models at all, return None."""
    registry = MagicMock()
    registry.get_verified_models.return_value = []
    registry.get_free_candidates.return_value = []
    registry.get_all_models.return_value = []

    rate_store = MagicMock()
    rate_store.is_unavailable.return_value = False
    rate_store.is_rate_limited.return_value = False

    result = _dynamic_switch_model(
        "deepseek-v4-flash", registry=registry, rate_store=rate_store,
    )
    assert result is None


# ---------------------------------------------------------------------------
# NEW: Catch-all rate-limit guard tests (Fix 1 + 3 — agent 1 & 3 findings)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_raises_when_only_model_is_rate_limited(
    mock_get_verified_models,
):
    """When _dynamic_switch_model returns None and the only model is rate-limited,
    _mark_and_refresh should raise RuntimeError, not return the rate-limited model."""
    mock_get_verified_models.return_value = ["the-only-model"]
    breaker = MagicMock()
    breaker.is_available.return_value = True
    rate_store = MagicMock()
    rate_store.is_rate_limited.return_value = True  # model is rate-limited

    with patch("src.llm.model_state._switch_model", return_value="the-only-model"):
        error = _make_rate_limit_error()
        with pytest.raises(RuntimeError, match="rate-limited"):
            _mark_and_refresh(
                "the-only-model", error=error, refresh=False,
                breaker=breaker, rate_store=rate_store,
            )


@pytest.mark.anyio
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_raises_when_fallback_is_also_rate_limited(
    mock_get_verified_models,
):
    """When _dynamic_switch_model returns None AND _switch_model returns a different
    model that is also rate-limited, raise instead of returning it."""
    mock_get_verified_models.return_value = ["model-a", "model-b"]
    breaker = MagicMock()
    breaker.is_available.return_value = True
    rate_store = MagicMock()
    # Both models rate-limited
    rate_store.is_rate_limited.return_value = True

    with patch("src.llm.model_state._switch_model", return_value="model-b"):
        error = _make_rate_limit_error()
        with pytest.raises(RuntimeError, match="rate-limited"):
            _mark_and_refresh(
                "model-a", error=error, refresh=False,
                breaker=breaker, rate_store=rate_store,
            )


@pytest.mark.anyio
async def test_mark_and_refresh_rate_limited_uses_dynamic_fallback():
    """When primary is rate-limited and a free model is available in the registry,
    _mark_and_refresh should return the free model."""
    registry = MagicMock()
    registry.get_verified_models.return_value = [
        "deepseek-v4-flash", "deepseek-v4-flash-free",
    ]
    registry.get_free_candidates.return_value = ["deepseek-v4-flash-free"]
    registry.get_all_models.return_value = [
        "deepseek-v4-flash", "deepseek-v4-flash-free",
    ]

    breaker = MagicMock()
    rate_store = MagicMock()
    rate_store.is_unavailable.return_value = False
    # Primary is rate-limited but not the free model
    def is_rate_limited(model: str) -> bool:
        return model == "deepseek-v4-flash"
    rate_store.is_rate_limited.side_effect = is_rate_limited

    with patch("src.llm.model_state.mark_model_failed") as mock_mark:
        result = _mark_and_refresh(
            "deepseek-v4-flash",
            error=_make_rate_limit_error(),
            refresh=False,
            breaker=breaker,
            rate_store=rate_store,
            registry=registry,
        )
        mock_mark.assert_not_called()
    assert result == "deepseek-v4-flash-free"


@pytest.mark.anyio
@patch("src.llm.discovery.get_verified_models")
async def test_mark_and_refresh_still_records_breaker_for_generic_error(
    mock_get_verified_models,
):
    """Breaker.record_failure should still be called for non-rate-limit errors."""
    mock_get_verified_models.return_value = ["model-a", "model-b"]
    breaker = MagicMock()
    rate_store = MagicMock()
    rate_store.is_rate_limited.return_value = False
    rate_store.is_unavailable.return_value = False

    with patch("src.llm.model_state._switch_model", return_value="model-b"):
        with patch("src.llm.model_state.mark_model_failed"):
            _mark_and_refresh(
                "model-a",
                error=_make_generic_error("server error"),
                refresh=False,
                breaker=breaker,
                rate_store=rate_store,
            )
    breaker.record_failure.assert_called_once_with("model-a")
