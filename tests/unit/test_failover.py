from unittest.mock import patch, MagicMock

import pytest

from src.llm.failover import _mark_and_refresh


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

    result = _mark_and_refresh("model1")

    mock_mark_model_failed.assert_called_once_with("model1")
    mock_switch_model.assert_called_once_with("model1")
    assert result == "model1"
