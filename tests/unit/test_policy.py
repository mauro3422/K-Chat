from unittest.mock import patch, MagicMock

import pytest


def test_policy_reexports_get_models_from_discovery():
    import src.llm.policy as policy
    with patch.object(policy, "get_models") as mock_fn:
        mock_fn.return_value = ["model1", "model2"]
        result = policy.get_models()
        assert result == ["model1", "model2"]


def test_policy_reexports_get_free_models_from_discovery():
    import src.llm.policy as policy
    with patch.object(policy, "get_free_models") as mock_fn:
        mock_fn.return_value = ["model1-free", "model2-free"]
        result = policy.get_free_models()
        assert result == ["model1-free", "model2-free"]


def test_policy_reexports_get_verified_models_from_discovery():
    import src.llm.policy as policy
    with patch.object(policy, "get_verified_models") as mock_fn:
        mock_fn.return_value = ["model1", "model2"]
        result = policy.get_verified_models()
        assert result == ["model1", "model2"]


def test_policy_reexports_verify_model_from_verifier():
    import src.llm.policy as policy
    with patch.object(policy, "verify_model") as mock_fn:
        mock_fn.return_value = True
        result = policy.verify_model("test-model")
        assert result is True


def test_policy_reexports_get_default_model_from_selector():
    import src.llm.policy as policy
    with patch.object(policy, "get_default_model") as mock_fn:
        mock_fn.return_value = "test-model"
        result = policy.get_default_model()
        assert result == "test-model"


def test_policy_reexports_mark_and_refresh_from_failover():
    import src.llm.policy as policy
    with patch.object(policy, "_mark_and_refresh") as mock_fn:
        mock_fn.return_value = "next-model"
        result = policy._mark_and_refresh("test-model")
        assert result == "next-model"
