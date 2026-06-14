from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock

import pytest

from src.llm.providers import (
    register_provider,
    _get_provider,
    _PROVIDER_REGISTRY,
)
from src.llm.protocol import LLMProvider


@pytest.mark.anyio
async def test_register_provider_adds_to_registry():
    from src.llm import providers
    original = providers._PROVIDER_REGISTRY.copy()
    try:
        providers._PROVIDER_REGISTRY.clear()
        mock_cls = MagicMock(spec=LLMProvider)
        register_provider("test", mock_cls)
        assert providers._PROVIDER_REGISTRY["test"] is mock_cls
    finally:
        providers._PROVIDER_REGISTRY.update(original)


@pytest.mark.anyio
async def test_get_provider_creates_provider_singleton():
    from src.llm import providers
    original_provider = providers._provider
    original_registry = providers._PROVIDER_REGISTRY.copy()
    try:
        providers._provider = None
        mock_cls = MagicMock(spec=LLMProvider)
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        providers._PROVIDER_REGISTRY["test"] = mock_cls

        with patch.object(providers, "DEFAULT_CONFIG") as mock_config:
            mock_config.llm_provider = "test"
            result = _get_provider()

        assert result is mock_instance
        assert providers._provider is mock_instance
    finally:
        providers._provider = original_provider
        providers._PROVIDER_REGISTRY.clear()
        providers._PROVIDER_REGISTRY.update(original_registry)


@pytest.mark.anyio
async def test_provider_registry_has_default_openai_provider():
    assert "openai" in _PROVIDER_REGISTRY


@pytest.mark.anyio
async def test_register_provider_overwrites_existing_entry():
    from src.llm import providers
    original = providers._PROVIDER_REGISTRY.copy()
    try:
        mock_cls1 = MagicMock(spec=LLMProvider)
        mock_cls2 = MagicMock(spec=LLMProvider)

        providers._PROVIDER_REGISTRY["openai"] = mock_cls1
        register_provider("openai", mock_cls1)
        assert providers._PROVIDER_REGISTRY["openai"] is mock_cls1

        register_provider("openai", mock_cls2)
        assert providers._PROVIDER_REGISTRY["openai"] is mock_cls2
    finally:
        providers._PROVIDER_REGISTRY.clear()
        providers._PROVIDER_REGISTRY.update(original)
