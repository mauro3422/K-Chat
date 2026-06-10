from typing import Protocol

from src.llm.protocol import LLMProvider


class TestLLMProviderProtocol:
    def test_is_protocol_subclass(self):
        assert issubclass(LLMProvider, Protocol)

    def test_is_runtime_checkable(self):
        assert hasattr(LLMProvider, "__instancecheck__")

    def test_openai_provider_satisfies(self):
        from src.llm.openai_provider import OpenAIProvider
        assert isinstance(OpenAIProvider(), LLMProvider)

    def test_mock_with_all_methods_passes(self):
        class MockProvider:
            def chat(self, messages, model, **kwargs):
                return None
            def chat_stream(self, messages, model, **kwargs):
                return (x for x in [])
            def list_models(self):
                return []
        assert isinstance(MockProvider(), LLMProvider)

    def test_mock_missing_chat_fails(self):
        class BadProvider:
            def chat_stream(self, messages, model, **kwargs):
                return (x for x in [])
            def list_models(self):
                return []
        assert not isinstance(BadProvider(), LLMProvider)

    def test_mock_missing_chat_stream_fails(self):
        class BadProvider:
            def chat(self, messages, model, **kwargs):
                return None
            def list_models(self):
                return []
        assert not isinstance(BadProvider(), LLMProvider)

    def test_mock_missing_list_models_fails(self):
        class BadProvider:
            def chat(self, messages, model, **kwargs):
                return None
            def chat_stream(self, messages, model, **kwargs):
                return (x for x in [])
        assert not isinstance(BadProvider(), LLMProvider)

    def test_mock_returns_generator_any(self):
        class MockProvider:
            def chat(self, messages, model, **kwargs):
                return None
            def chat_stream(self, messages, model, **kwargs):
                return iter([1, 2, 3])
            def list_models(self):
                return []
        assert isinstance(MockProvider(), LLMProvider)

    def test_plain_object_with_methods_passes(self):
        obj = type("", (), {
            "chat": lambda self, m, model, **kw: None,
            "chat_stream": lambda self, m, model, **kw: (x for x in []),
            "list_models": lambda self: [],
        })()
        assert isinstance(obj, LLMProvider)
