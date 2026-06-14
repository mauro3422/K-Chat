from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock

import pytest

from src.llm.selector import get_default_model, _get_default_model_candidates


@patch("src.llm.model_state.get_verified_models_safe")
@patch("src.llm.model_state.is_model_failed")
@patch("src.llm.model_state.PRIORITY", ["big-pickle", "deepseek-v4-flash-free"])
@pytest.mark.anyio
async def test_get_default_model_returns_first_available_priority_model_from_verified_list(
    mock_is_model_failed, mock_get_verified_models_safe
):
    mock_get_verified_models_safe.return_value = ["big-pickle", "deepseek-v4-flash-free"]
    mock_is_model_failed.side_effect = [False, False]

    result = get_default_model()

    assert result == "big-pickle"


@patch("src.llm.model_state.get_verified_models_safe")
@patch("src.llm.model_state.is_model_failed")
@patch("src.llm.discovery.get_free_models")
@patch("src.llm.model_state.PRIORITY", ["big-pickle", "deepseek-v4-flash-free"])
@patch("src.llm.model_state.FALLBACK_MODEL", "deepseek-v4-flash-free")
@pytest.mark.anyio
async def test_get_default_model_falls_back_to_free_models_when_no_verified_models(
    mock_get_free_models, mock_is_model_failed, mock_get_verified_models_safe
):
    mock_get_verified_models_safe.return_value = None
    mock_is_model_failed.side_effect = [True, True]
    mock_model1 = MagicMock()
    mock_model1.id = "model1-free"
    mock_model2 = MagicMock()
    mock_model2.id = "model2-free"
    mock_get_free_models.return_value = [mock_model1, mock_model2]

    result = get_default_model()

    assert result == "deepseek-v4-flash-free"


@patch("src.llm.model_state.get_verified_models_safe")
@patch("src.llm.model_state.is_model_failed")
@patch("src.llm.model_state.FALLBACK_MODEL", "deepseek-v4-flash-free")
@pytest.mark.anyio
async def test_get_default_model_returns_fallback_model_on_error(
    mock_is_model_failed, mock_get_verified_models_safe
):
    mock_get_verified_models_safe.side_effect = Exception("Error")
    mock_is_model_failed.side_effect = [False, False]

    result = get_default_model()

    assert result == "deepseek-v4-flash-free"


@patch("src.llm.model_state.get_verified_models_safe")
@patch("src.llm.model_state.is_model_failed")
@patch("src.llm.model_state.FALLBACK_MODEL", "deepseek-v4-flash-free")
@patch("src.llm.model_state.PRIORITY", ["big-pickle", "deepseek-v4-flash-free"])
@pytest.mark.anyio
async def test_get_default_model_handles_all_models_failed_gracefully(
    mock_is_model_failed, mock_get_verified_models_safe
):
    mock_get_verified_models_safe.return_value = ["big-pickle", "deepseek-v4-flash-free"]
    mock_is_model_failed.side_effect = [True, True]

    result = get_default_model()

    assert result == "deepseek-v4-flash-free"


@patch("src.llm.model_state.get_verified_models_safe")
@pytest.mark.anyio
async def test_get_default_model_candidates_returns_cached_verified_list(mock_get_verified_models_safe):
    mock_get_verified_models_safe.return_value = ["model1", "model2"]

    result, verified_cache_used = _get_default_model_candidates()

    assert result == ["model1", "model2"]
    assert verified_cache_used is True


@patch("src.llm.model_state.get_verified_models_safe")
@patch("src.llm.discovery.get_free_models")
@pytest.mark.anyio
async def test_get_default_model_candidates_returns_free_models_when_no_cache(
    mock_get_free_models, mock_get_verified_models_safe
):
    mock_get_verified_models_safe.return_value = None
    mock_model1 = MagicMock()
    mock_model1.id = "model1-free"
    mock_model2 = MagicMock()
    mock_model2.id = "model2-free"
    mock_get_free_models.return_value = [mock_model1, mock_model2]

    result, verified_cache_used = _get_default_model_candidates()

    assert result == ["model1-free", "model2-free"]
    assert verified_cache_used is False
