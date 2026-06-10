from unittest.mock import patch, MagicMock
from collections.abc import Generator
import pytest

from src.llm.openai_provider import OpenAIProvider, _DEFAULT_BASE_URL


class TestOpenAIProviderConstructor:
    def test_passes_api_key_and_base_url(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            OpenAIProvider(api_key="my-key", base_url="https://my.url")
            mock_openai.assert_called_once_with(api_key="my-key", base_url="https://my.url")

    def test_uses_default_base_url_when_not_provided(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            OpenAIProvider(api_key="my-key")
            mock_openai.assert_called_once_with(api_key="my-key", base_url=_DEFAULT_BASE_URL)


class TestOpenAIProviderChat:
    def test_calls_completions_create(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            provider.chat([{"role": "user", "content": "Hi"}], model="gpt-4")

            mock_client.chat.completions.create.assert_called_once_with(
                model="gpt-4", messages=[{"role": "user", "content": "Hi"}]
            )

    def test_passes_kwargs(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            provider.chat([], model="gpt-4", temperature=0.5, max_tokens=100)

            mock_client.chat.completions.create.assert_called_once_with(
                model="gpt-4", messages=[], temperature=0.5, max_tokens=100
            )

    def test_returns_response(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            expected = MagicMock()
            mock_client.chat.completions.create.return_value = expected
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            result = provider.chat([], model="gpt-4")

            assert result is expected

    def test_propagates_exception(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("API down")
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            with pytest.raises(Exception, match="API down"):
                provider.chat([], model="gpt-4")


class TestOpenAIProviderChatStream:
    def test_calls_completions_create_with_stream(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            provider.chat_stream([{"role": "user", "content": "Hi"}], model="gpt-4")

            mock_client.chat.completions.create.assert_called_once_with(
                model="gpt-4", messages=[{"role": "user", "content": "Hi"}], stream=True
            )

    def test_passes_kwargs(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            provider.chat_stream([], model="gpt-4", temperature=0.5)

            mock_client.chat.completions.create.assert_called_once_with(
                model="gpt-4", messages=[], stream=True, temperature=0.5
            )

    def test_returns_generator(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            expected = iter(["chunk1", "chunk2"])
            mock_client.chat.completions.create.return_value = expected
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            result = provider.chat_stream([], model="gpt-4")

            assert isinstance(result, Generator) or hasattr(result, "__next__")
            assert list(result) == ["chunk1", "chunk2"]

    def test_propagates_exception(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("stream error")
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            with pytest.raises(Exception, match="stream error"):
                provider.chat_stream([], model="gpt-4")


class TestOpenAIProviderListModels:
    def test_returns_model_list(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.models.list.return_value = ["model-a", "model-b"]
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            result = provider.list_models()

            assert result == ["model-a", "model-b"]
            mock_client.models.list.assert_called_once()

    def test_propagates_exception(self):
        with patch("src.llm.openai_provider.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.models.list.side_effect = Exception("list error")
            provider = OpenAIProvider(api_key="key", base_url="https://url")

            with pytest.raises(Exception, match="list error"):
                provider.list_models()
