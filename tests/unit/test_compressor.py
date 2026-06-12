from unittest.mock import MagicMock, patch

from src.compressor import (
    should_compress,
    compress_history,
    MAX_HISTORY,
    KEEP_RECENT,
)


def make_msg(role="user", content="hello"):
    return {"role": role, "content": content}


class TestShouldCompress:

    def test_empty_history(self):
        assert should_compress([]) is False

    def test_under_max_history_and_under_token_limit(self):
        history = [make_msg(content="short") for _ in range(MAX_HISTORY - 1)]
        assert should_compress(history) is False

    def test_over_max_history_even_with_few_tokens(self):
        history = [make_msg(content="a") for _ in range(MAX_HISTORY + 5)]
        assert should_compress(history) is True

    def test_under_max_history_but_over_token_limit(self):
        chars_per_msg = 1000
        count = 25
        history = [make_msg(content="x" * chars_per_msg) for _ in range(count)]
        assert len(history) < MAX_HISTORY
        assert should_compress(history) is True

    def test_exactly_at_max_history_boundary(self):
        history = [make_msg() for _ in range(MAX_HISTORY + 1)]
        assert len(history) == MAX_HISTORY + 1
        assert should_compress(history) is True


class TestCompressHistory:

    def test_nothing_to_compress(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg() for _ in range(KEEP_RECENT)]
        original = list(history)

        compress_history(history, "test-model")

        assert history == original

    def test_compression_with_llm(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg(content=f"msg {i}") for i in range(20)]
        recent = history[-KEEP_RECENT:]
        system = history[0]

        mock_response = MagicMock()
        mock_response.message.content = "Test summary"
        mock_llm = MagicMock(return_value=mock_response)
        compress_history(history, "test-model", chat_fn=mock_llm)

        mock_llm.assert_called_once()
        assert len(history) == 1 + 1 + KEEP_RECENT
        assert history[0] == system
        assert history[1] == {"role": "system", "content": "[Resumen: Test summary]"}
        assert history[2:] == recent

    def test_llm_exception(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg(content=f"msg {i}") for i in range(20)]
        original = list(history)

        mock_llm = MagicMock(side_effect=RuntimeError("LLM error"))
        compress_history(history, "test-model", chat_fn=mock_llm)

        assert history == original

    def test_empty_summary_from_llm(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg(content=f"msg {i}") for i in range(20)]
        original = list(history)

        mock_response = MagicMock()
        mock_response.message.content = None
        mock_llm = MagicMock(return_value=mock_response)
        compress_history(history, "test-model", chat_fn=mock_llm)

        assert history == original
