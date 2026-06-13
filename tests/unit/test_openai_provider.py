from unittest.mock import patch, MagicMock
from collections.abc import Generator
import pytest

from src.llm.adapters.openai_adapter import OpenAIAdapter
from src.llm.protocol import UnifiedRequest


class TestOpenAIAdapterConstructor:
    def test_passes_api_key_and_base_url(self):
        with patch("src.llm.adapters.openai_adapter.OpenAI") as mock_openai:
            OpenAIAdapter(api_key="my-key", base_url="https://my.url")
            call_kwargs = mock_openai.call_args.kwargs
            assert call_kwargs["api_key"] == "my-key"
            assert call_kwargs["base_url"] == "https://my.url"
            assert "timeout" in call_kwargs
            assert call_kwargs["max_retries"] == 0

    def test_provider_name(self):
        with patch("src.llm.adapters.openai_adapter.OpenAI"):
            provider = OpenAIAdapter(api_key="key", base_url="https://url")
            assert provider.provider_name == "openai"

    def test_supports_flags(self):
        with patch("src.llm.adapters.openai_adapter.OpenAI"):
            provider = OpenAIAdapter(api_key="key", base_url="https://url")
            assert provider.supports_streaming is True
            assert provider.supports_tools is True
            assert provider.supports_reasoning is True


class TestOpenAIProviderChat:
    def test_calls_completions_create(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            request = UnifiedRequest(
                messages=[{"role": "user", "content": "Hi"}],
                model="gpt-4",
            )
            provider.chat(request)

            mock_client.chat.completions.create.assert_called_once_with(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hi"}],
                tools=None,
                stream=False,
                temperature=None,
                max_tokens=None,
            )

    def test_returns_unified_response(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Hello"
            mock_response.choices[0].message.tool_calls = None
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            mock_client.chat.completions.create.return_value = mock_response

            provider = OpenAIProvider(api_key="key", base_url="https://url")
            request = UnifiedRequest(messages=[{"role": "user", "content": "Hi"}], model="gpt-4")
            result = provider.chat(request)

            assert result.content == "Hello"
            assert result.finish_reason == "stop"
            assert result.model == "gpt-4"
            assert result.usage.prompt_tokens == 10


class TestOpenAIProviderChatStream:
    def test_calls_completions_create_with_stream(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = iter([])

            provider = OpenAIProvider(api_key="key", base_url="https://url")
            request = UnifiedRequest(
                messages=[{"role": "user", "content": "Hi"}],
                model="gpt-4",
            )
            list(provider.chat_stream(request))

            mock_client.chat.completions.create.assert_called_once_with(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hi"}],
                tools=None,
                stream=True,
                stream_options={"include_usage": True},
                temperature=None,
                max_tokens=None,
            )

    def test_returns_generator(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = iter([])

            provider = OpenAIProvider(api_key="key", base_url="https://url")
            request = UnifiedRequest(messages=[], model="gpt-4")
            result = provider.chat_stream(request)

            assert isinstance(result, Generator) or hasattr(result, "__next__")


class TestOpenAIProviderListModels:
    def test_returns_model_list(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.models.list.return_value = [MagicMock(id="model-a"), MagicMock(id="model-b")]

            provider = OpenAIProvider(api_key="key", base_url="https://url")
            result = provider.list_models()

            assert result == ["model-a", "model-b"]
            mock_client.models.list.assert_called_once()
