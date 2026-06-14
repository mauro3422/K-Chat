import pytest
from unittest.mock import AsyncMock
from typing import Protocol

from src.llm.protocol import LLMProvider, UnifiedRequest, UnifiedResponse


class TestLLMProviderProtocol:
    @pytest.mark.anyio
    async def test_is_protocol_subclass(self):
        assert issubclass(LLMProvider, Protocol)

    @pytest.mark.anyio
    async def test_is_runtime_checkable(self):
        assert hasattr(LLMProvider, "__instancecheck__")

    @pytest.mark.anyio
    async def test_openai_provider_satisfies(self):
        from src.llm.adapters.openai_adapter import OpenAIAdapter
        assert isinstance(OpenAIAdapter(api_key="test", base_url="https://test"), LLMProvider)

    @pytest.mark.anyio
    async def test_mock_with_all_methods_passes(self):
        class MockProvider:
            @property
            def provider_name(self):
                return "mock"

            @property
            def supports_streaming(self):
                return True

            @property
            def supports_tools(self):
                return True

            @property
            def supports_reasoning(self):
                return False

            def chat(self, request):
                return None

            def chat_stream(self, request):
                return (x for x in [])

            def list_models(self):
                return []
        assert isinstance(MockProvider(), LLMProvider)

    @pytest.mark.anyio
    async def test_mock_missing_chat_fails(self):
        class BadProvider:
            @property
            def provider_name(self):
                return "bad"

            @property
            def supports_streaming(self):
                return True

            @property
            def supports_tools(self):
                return True

            @property
            def supports_reasoning(self):
                return False

            def chat_stream(self, request):
                return (x for x in [])

            def list_models(self):
                return []
        assert not isinstance(BadProvider(), LLMProvider)

    @pytest.mark.anyio
    async def test_mock_missing_chat_stream_fails(self):
        class BadProvider:
            @property
            def provider_name(self):
                return "bad"

            @property
            def supports_streaming(self):
                return True

            @property
            def supports_tools(self):
                return True

            @property
            def supports_reasoning(self):
                return False

            def chat(self, request):
                return None

            def list_models(self):
                return []
        assert not isinstance(BadProvider(), LLMProvider)

    @pytest.mark.anyio
    async def test_mock_missing_list_models_fails(self):
        class BadProvider:
            @property
            def provider_name(self):
                return "bad"

            @property
            def supports_streaming(self):
                return True

            @property
            def supports_tools(self):
                return True

            @property
            def supports_reasoning(self):
                return False

            def chat(self, request):
                return None

            def chat_stream(self, request):
                return (x for x in [])
        assert not isinstance(BadProvider(), LLMProvider)

    @pytest.mark.anyio
    async def test_mock_returns_generator_any(self):
        class MockProvider:
            @property
            def provider_name(self):
                return "mock"

            @property
            def supports_streaming(self):
                return True

            @property
            def supports_tools(self):
                return True

            @property
            def supports_reasoning(self):
                return False

            def chat(self, request):
                return None

            def chat_stream(self, request):
                return iter([1, 2, 3])

            def list_models(self):
                return []
        assert isinstance(MockProvider(), LLMProvider)

    @pytest.mark.anyio
    async def test_plain_object_with_methods_passes(self):
        obj = type("", (), {
            "provider_name": property(lambda self: "plain"),
            "supports_streaming": property(lambda self: True),
            "supports_tools": property(lambda self: True),
            "supports_reasoning": property(lambda self: False),
            "chat": lambda self, req: None,
            "chat_stream": lambda self, req: (x for x in []),
            "list_models": lambda self: [],
        })()
        assert isinstance(obj, LLMProvider)
