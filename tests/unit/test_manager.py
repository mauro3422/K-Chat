from unittest.mock import patch, MagicMock
import pytest

from src.llm.policy import (
    verify_model,
    get_verified_models,
    get_models,
    get_free_models,
    get_default_model,
    _mark_and_refresh,
)


class TestVerifyModel:
    @patch("src.llm.verifier.models._api_call")
    def test_returns_true_on_success(self, mock_api_call):
        mock_api_call.return_value = MagicMock()
        assert verify_model("deepseek-v4-flash-free") is True
        mock_api_call.assert_called_once_with(
            model="deepseek-v4-flash-free",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=2,
            timeout=2.0,
        )

    @patch("src.llm.verifier.models._api_call")
    def test_returns_false_on_exception(self, mock_api_call):
        mock_api_call.side_effect = Exception("API error")
        assert verify_model("bad-model") is False


class TestGetModels:
    @patch("src.llm.discovery.models.set_cached_models")
    @patch("src.llm.discovery.models.get_cached_models_safe")
    def test_fetches_from_api_when_cache_empty(
        self, mock_get_cache, mock_set_cache
    ):
        mock_provider = MagicMock()
        mock_provider.list_models.return_value = ["model1", "model2"]
        mock_get_cache.side_effect = [None, ["model1", "model2"]]
        with patch("src.llm.discovery.models._get_provider", return_value=mock_provider):
            result = get_models()
        mock_provider.list_models.assert_called_once()
        mock_set_cache.assert_called_once_with(["model1", "model2"])
        assert result == ["model1", "model2"]

    @patch("src.llm.discovery.models.get_cached_models_safe")
    def test_returns_cached_when_available(self, mock_get_cache):
        mock_get_cache.return_value = ["cached1", "cached2"]

        result = get_models()

        assert result == ["cached1", "cached2"]

    @patch("src.llm.discovery.models.set_cached_models")
    @patch("src.llm.discovery.models.get_cached_models_safe")
    def test_forces_refresh(self, mock_get_cache, mock_set_cache):
        mock_provider = MagicMock()
        mock_provider.list_models.return_value = ["fresh1"]
        mock_get_cache.side_effect = [["cached"], ["fresh1"]]
        with patch("src.llm.discovery.models._get_provider", return_value=mock_provider):
            result = get_models(force_refresh=True)
        mock_provider.list_models.assert_called_once()
        assert result == ["fresh1"]

    @patch("src.llm.discovery.models.get_cached_models_safe")
    def test_fallback_to_cache_on_api_error(self, mock_get_cache):
        mock_provider = MagicMock()
        mock_provider.list_models.side_effect = Exception("API down")
        mock_get_cache.side_effect = [None, ["old_cache"]]
        with patch("src.llm.discovery.models._get_provider", return_value=mock_provider):
            result = get_models()
        assert result == ["old_cache"]

    @patch("src.llm.discovery.models.get_cached_models_safe")
    def test_raises_when_no_cache_and_api_fails(self, mock_get_cache):
        mock_provider = MagicMock()
        mock_provider.list_models.side_effect = Exception("API down")
        mock_get_cache.return_value = None
        with patch("src.llm.discovery.models._get_provider", return_value=mock_provider):
            with pytest.raises(Exception, match="API down"):
                get_models()


class TestGetFreeModels:
    @patch("src.llm.discovery.get_models")
    def test_filters_free_models(self, mock_get_models):
        mock_m1 = MagicMock()
        mock_m1.id = "model-free"
        mock_m2 = MagicMock()
        mock_m2.id = "model-paid"
        mock_m3 = MagicMock()
        mock_m3.id = "other-free"
        mock_get_models.return_value = [mock_m1, mock_m2, mock_m3]

        result = get_free_models()

        assert len(result) == 2
        assert result[0].id == "model-free"
        assert result[1].id == "other-free"


class TestGetVerifiedModels:
    @patch("src.llm.discovery.models.get_verified_models_safe")
    def test_returns_cached_when_available(self, mock_get_verified):
        mock_get_verified.return_value = ["deepseek-v4-flash-free"]

        result = get_verified_models()

        assert result == ["deepseek-v4-flash-free"]

    @patch("src.llm.discovery.get_free_models")
    @patch("src.llm.verifier.verify_model")
    @patch("src.llm.discovery.models.set_verified_models")
    @patch("src.llm.discovery.models.get_verified_models_safe")
    def test_verifies_free_models(
        self, mock_get_verified, mock_set_verified, mock_verify, mock_get_free
    ):
        mock_get_verified.side_effect = [None, ["good-free"]]
        mock_m1 = MagicMock()
        mock_m1.id = "good-free"
        mock_m2 = MagicMock()
        mock_m2.id = "bad-free"
        mock_get_free.return_value = [mock_m1, mock_m2]
        mock_verify.side_effect = [True, False]

        result = get_verified_models()

        assert result == ["good-free"]
        mock_set_verified.assert_called_once_with(["good-free"])

    @patch("src.llm.discovery.get_free_models")
    @patch("src.llm.verifier.verify_model")
    @patch("src.llm.discovery.models.set_verified_models")
    @patch("src.llm.discovery.models.get_verified_models_safe")
    def test_forces_refresh(
        self, mock_get_verified, mock_set_verified, mock_verify, mock_get_free
    ):
        mock_get_verified.side_effect = [["cached"], ["m1-free"]]
        mock_m1 = MagicMock()
        mock_m1.id = "m1-free"
        mock_get_free.return_value = [mock_m1]
        mock_verify.return_value = True

        result = get_verified_models(force_refresh=True)

        mock_get_free.assert_called_once_with(force_refresh=True)
        assert result == ["m1-free"]

    @patch("src.llm.discovery.get_free_models")
    @patch("src.llm.discovery.models.set_verified_models")
    @patch("src.llm.discovery.models.get_verified_models_safe")
    def test_fallback_on_error(
        self, mock_get_verified, mock_set_verified, mock_get_free
    ):
        mock_get_verified.side_effect = [None, ["fallback_model"]]
        mock_get_free.side_effect = Exception("API error")

        result = get_verified_models()

        assert result == ["fallback_model"]

    @patch("src.llm.discovery.get_free_models")
    @patch("src.llm.discovery.models.set_verified_models")
    @patch("src.llm.discovery.models.get_verified_models_safe")
    def test_uses_fallback_model_when_no_cache(
        self, mock_get_verified, mock_set_verified, mock_get_free
    ):
        mock_get_verified.side_effect = [None, None, None]
        mock_get_free.side_effect = Exception("API error")

        result = get_verified_models()

        mock_set_verified.assert_called_once_with(["deepseek-v4-flash-free"])
        assert result == []


class TestGetDefaultModel:
    @patch("src.llm.selector.models.is_model_failed")
    @patch("src.llm.selector.models.get_verified_models_safe")
    @patch("src.llm.discovery.get_free_models")
    def test_returns_priority_model_when_available(self, mock_get_free, mock_get_verified, mock_failed):
        mock_get_verified.return_value = None
        mock_m1 = MagicMock()
        mock_m1.id = "big-pickle"
        mock_m2 = MagicMock()
        mock_m2.id = "deepseek-v4-flash-free"
        mock_get_free.return_value = [mock_m1, mock_m2]
        mock_failed.return_value = False

        result = get_default_model()

        assert result == "deepseek-v4-flash-free"

    @patch("src.llm.selector.models.is_model_failed")
    @patch("src.llm.selector.models.get_verified_models_safe")
    @patch("src.llm.discovery.get_free_models")
    def test_skips_failed_model(self, mock_get_free, mock_get_verified, mock_failed):
        mock_get_verified.return_value = None
        mock_m1 = MagicMock()
        mock_m1.id = "big-pickle"
        mock_m2 = MagicMock()
        mock_m2.id = "deepseek-v4-flash-free"
        mock_get_free.return_value = [mock_m1, mock_m2]
        mock_failed.side_effect = lambda m: m == "big-pickle"

        result = get_default_model()

        assert result == "deepseek-v4-flash-free"

    @patch("src.llm.discovery.get_free_models")
    def test_returns_fallback_on_error(self, mock_get_free):
        mock_get_free.side_effect = Exception("API error")

        result = get_default_model()

        assert result == "deepseek-v4-flash-free"

    @patch("src.llm.selector.models.is_model_failed")
    @patch("src.llm.selector.models.get_verified_models_safe")
    @patch("src.llm.discovery.get_free_models")
    def test_prefers_deepseek_even_when_big_pickle_is_available(self, mock_get_free, mock_get_verified, mock_failed):
        mock_get_verified.return_value = None
        mock_m1 = MagicMock()
        mock_m1.id = "deepseek-v4-flash-free"
        mock_get_free.return_value = [mock_m1]
        mock_failed.return_value = False

        result = get_default_model()

        assert result == "deepseek-v4-flash-free"

    @patch("src.llm.selector.models.is_model_failed")
    @patch("src.llm.selector.models.get_verified_models_safe")
    @patch("src.llm.discovery.get_free_models")
    def test_prefers_verified_cache_when_available(self, mock_get_free, mock_get_verified, mock_failed):
        mock_get_verified.return_value = ["deepseek-v4-flash-free"]
        mock_failed.return_value = False

        result = get_default_model()

        mock_get_free.assert_not_called()
        assert result == "deepseek-v4-flash-free"


class TestMarkAndRefresh:
    @patch("src.llm.failover.models._switch_model")
    @patch("src.llm.failover.models.mark_model_failed")
    @patch("src.llm.discovery.get_verified_models")
    def test_marks_and_switches(self, mock_verify, mock_mark, mock_switch):
        mock_switch.return_value = "deepseek-v4-flash-free"

        result = _mark_and_refresh("big-pickle")

        mock_verify.assert_called_once_with(force_refresh=True)
        mock_mark.assert_called_once_with("big-pickle")
        mock_switch.assert_called_once_with("big-pickle")
        assert result == "deepseek-v4-flash-free"

    @patch("src.llm.failover.models._switch_model")
    @patch("src.llm.failover.models.mark_model_failed")
    @patch("src.llm.discovery.get_verified_models")
    def test_handles_verify_failure(self, mock_verify, mock_mark, mock_switch):
        mock_verify.side_effect = Exception("verify error")
        mock_switch.return_value = "fallback"

        result = _mark_and_refresh("big-pickle")

        mock_verify.assert_called_once_with(force_refresh=True)
        mock_mark.assert_called_once_with("big-pickle")
        assert result == "fallback"

    @patch("src.llm.failover.models._switch_model")
    @patch("src.llm.failover.models.mark_model_failed")
    @patch("src.llm.discovery.get_verified_models")
    def test_can_skip_refresh(self, mock_verify, mock_mark, mock_switch):
        mock_switch.return_value = "fallback"

        result = _mark_and_refresh("big-pickle", refresh=False)

        mock_verify.assert_not_called()
        mock_mark.assert_called_once_with("big-pickle")
        mock_switch.assert_called_once_with("big-pickle")
        assert result == "fallback"
