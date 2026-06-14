from unittest.mock import AsyncMock, ANY
from unittest.mock import patch, MagicMock

import pytest

from src.llm.providers import (
    ProviderRegistry,
    register_provider,
    _get_provider,
    _get_registry,
)
from src.llm.protocol import LLMProvider


@pytest.mark.anyio
async def test_register_provider_adds_to_registry():
    registry = ProviderRegistry()
    mock_cls = MagicMock(spec=LLMProvider)
    registry.register("test", mock_cls)
    assert registry.get("test") is mock_cls


@pytest.mark.anyio
@patch("src.llm.providers._get_registry")
@patch("src.llm.providers._provider", None)
async def test_get_provider_creates_provider_singleton(mock_get_registry):
    mock_cls = MagicMock(spec=LLMProvider)
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance

    registry = ProviderRegistry()
    registry.register("test", mock_cls)
    mock_get_registry.return_value = registry

    mock_config = MagicMock()
    mock_config.llm_provider = "test"
    result = _get_provider(config=mock_config)

    assert result is mock_instance


@pytest.mark.anyio
async def test_provider_registry_has_default_openai_provider():
    assert _get_registry().get("openai") is not None


@pytest.mark.anyio
async def test_register_provider_overwrites_existing_entry():
    registry = ProviderRegistry()
    mock_cls1 = MagicMock(spec=LLMProvider)
    mock_cls2 = MagicMock(spec=LLMProvider)

    registry.register("openai", mock_cls1)
    assert registry.get("openai") is mock_cls1

    registry.register("openai", mock_cls2)
    assert registry.get("openai") is mock_cls2
