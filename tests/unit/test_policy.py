from unittest.mock import patch, MagicMock

import pytest

from src.llm.discovery import get_models, get_free_models, get_verified_models
from src.llm.verifier import verify_model
from src.llm.selector import get_default_model
from src.llm.failover import _mark_and_refresh


def test_get_models():
    with patch("src.llm.discovery.models.get_cached_models_safe") as mock_fn:
        mock_fn.return_value = ["model1", "model2"]
        result = get_models()
        assert result == ["model1", "model2"]


def test_get_free_models():
    with patch("src.llm.discovery.get_models") as mock_fn:
        mock_m1 = MagicMock(id="model1-free")
        mock_m2 = MagicMock(id="model2-free")
        mock_fn.return_value = [mock_m1, mock_m2]
        result = get_free_models()
        assert [m.id for m in result] == ["model1-free", "model2-free"]


def test_get_verified_models():
    with patch("src.llm.discovery.models.get_verified_models_safe") as mock_cache:
        mock_cache.return_value = ["model1"]
        result = get_verified_models()
        assert result == ["model1"]


def test_verify_model():
    with patch("src.llm.verifier.api_call") as mock_fn:
        mock_fn._api_call.return_value = MagicMock()
        assert verify_model("test-model") is True


def test_get_default_model():
    with patch("src.llm.selector.models.is_model_failed") as mock_failed:
        with patch("src.llm.selector.models.get_verified_models_safe") as mock_verified:
            with patch("src.llm.discovery.get_free_models") as mock_free:
                mock_verified.return_value = None
                mock_free.return_value = [MagicMock(id="deepseek-v4-flash-free")]
                mock_failed.return_value = False
                assert get_default_model() == "deepseek-v4-flash-free"


def test_mark_and_refresh():
    with patch("src.llm.failover.discovery.get_verified_models") as mock_refresh:
        with patch("src.llm.failover.models.mark_model_failed") as mock_failed:
            with patch("src.llm.failover.models._switch_model") as mock_switch:
                mock_switch.return_value = "next-model"
                result = _mark_and_refresh("test-model")
                assert result == "next-model"
