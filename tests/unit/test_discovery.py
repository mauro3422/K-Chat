from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.llm.model_state import clear_failed_models, set_cached_models
from src.llm.model_registry import set_verified_models
from src.llm.discovery import get_models, get_free_models, get_verified_models


@pytest.fixture(autouse=True)
def clear_llm_state():
    clear_failed_models()
    set_cached_models(None)
    set_verified_models(None)
    yield


@pytest.mark.anyio
@patch("src.llm.discovery._get_provider")
@patch("src.llm.discovery.models.get_cached_models_safe")
async def test_get_models_returns_cached_models(mock_get_cached, mock_get_provider):
    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_model.id = "test-model-free"
    mock_provider.list_models.return_value = [mock_model]
    mock_get_provider.return_value = mock_provider
    mock_get_cached.return_value = [mock_model]

    result = await get_models()
    assert result == [mock_model]
    mock_provider.list_models.assert_not_called()


@pytest.mark.anyio
@patch("src.llm.discovery._get_provider")
@patch("src.llm.discovery.models.get_cached_models_safe")
async def test_get_models_fetches_from_api_when_no_cache(mock_get_cached, mock_get_provider):
    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_model.id = "test-model-free"
    mock_provider.list_models.return_value = [mock_model]
    mock_get_provider.return_value = mock_provider
    mock_get_cached.side_effect = [None, [mock_model]]

    result = await get_models()
    assert result == [mock_model]
    mock_provider.list_models.assert_called_once()


@pytest.mark.anyio
@patch("src.llm.discovery._get_provider")
@patch("src.llm.discovery.models.get_cached_models_safe")
async def test_get_models_handles_api_errors_using_cache_fallback(mock_get_cached, mock_get_provider):
    mock_provider = MagicMock()
    mock_model = MagicMock()
    mock_model.id = "test-model-free"
    mock_provider.list_models.side_effect = Exception("API error")
    mock_get_provider.return_value = mock_provider
    mock_get_cached.side_effect = [[mock_model], [mock_model]]

    result = await get_models()
    assert result == [mock_model]


@pytest.mark.anyio
@patch("src.llm.discovery.get_models", new_callable=AsyncMock)
async def test_get_free_models_filters_by_free_suffix(mock_get_models):
    mock_model1 = MagicMock()
    mock_model1.id = "model-free"
    mock_model2 = MagicMock()
    mock_model2.id = "model-pro"
    mock_get_models.return_value = [mock_model1, mock_model2]

    result = await get_free_models()
    assert result == [mock_model1]


@pytest.mark.anyio
@patch("src.llm.discovery._is_go_mode", return_value=False)
@patch("src.llm.verifier.verify_model", new_callable=AsyncMock)
@patch("src.llm.discovery.get_free_models", new_callable=AsyncMock)
async def test_get_verified_models_verifies_free_models_in_parallel(
    mock_get_free_models, mock_verify_model, mock_is_go
):
    mock_model1 = MagicMock()
    mock_model1.id = "model1-free"
    mock_model2 = MagicMock()
    mock_model2.id = "model2-free"
    mock_get_free_models.return_value = [mock_model1, mock_model2]

    mock_verify_model.side_effect = [True, False]

    result = await get_verified_models()
    assert result == ["model1-free"]
    assert mock_verify_model.call_count == 2
