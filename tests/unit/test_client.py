from unittest.mock import ANY, AsyncMock
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
from collections.abc import AsyncIterator
import json
import pytest

from src.core.debug_info import DebugInfo
from src.llm.client import (
    chat,
    chat_stream,
    _resolve_model,
    _update_system_prompt,
    _process_chunks,
    _process_tool_delta,
    _update_debug_usage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(gen):
    """Exhaust a sync or async generator and return (yielded_items, return_value)."""
    if hasattr(gen, '__aiter__'):
        items = []
        try:
            while True:
                items.append(await gen.__anext__())
        except StopAsyncIteration:
            pass
        return items, None
    items = []
    try:
        while True:
            items.append(next(gen))
    except StopIteration as e:
        return items, e.value


def _make_delta(content=None, reasoning=None, tool_calls=None):
    delta = MagicMock()
    delta.content = content
    delta.reasoning_content = reasoning
    delta.reasoning = reasoning
    delta.tool_calls = tool_calls
    return delta


def _make_chunk(delta=None, usage=None):
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    if usage is not None:
        chunk.usage = usage
    else:
        usage_obj = MagicMock()
        usage_obj.prompt_tokens = 0
        usage_obj.completion_tokens = 0
        usage_obj.total_tokens = 0
        chunk.usage = usage_obj
    return chunk


class _AsyncListIterator:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0
    def __aiter__(self):
        return self
    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class _AsyncErrorIterator:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise Exception("Model big-pickle is not supported")


class _AsyncPartialThenErrorIterator:
    def __init__(self, item):
        self._item = item
        self._yielded = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._yielded:
            self._yielded = True
            return self._item
        raise Exception("connection lost mid-stream")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_models():
    with patch("src.llm.client.models") as m:
        yield m


@pytest.fixture
def mock_policy():
    with patch("src.llm.client.get_default_model") as m:
        yield m


@pytest.fixture
def mock_api_call():
    with patch("src.llm.client.api_call") as m:
        m._api_call = AsyncMock()
        yield m


@pytest.fixture
def mock_retry():
    with patch("src.llm.client.is_rate_limit_error") as m:
        yield m


@pytest.fixture
def mock_failover():
    with patch("src.llm.client._mark_and_refresh") as m:
        yield m


# ===================================================================
# _update_debug_usage
# ===================================================================

class TestUpdateDebugUsage:
    @pytest.mark.anyio
    async def test_updates_debug_dict(self):
        chunk = MagicMock()
        chunk.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        debug = DebugInfo()
        _update_debug_usage(chunk, debug)
        assert debug.prompt_tokens == 1
        assert debug.completion_tokens == 2
        assert debug.total_tokens == 3

    @pytest.mark.anyio
    async def test_skips_when_no_usage(self):
        chunk = MagicMock()
        chunk.usage = None
        debug = DebugInfo()
        _update_debug_usage(chunk, debug)
        assert debug.prompt_tokens == 0

    @pytest.mark.anyio
    async def test_no_error_when_debug_is_none(self):
        chunk = MagicMock()
        chunk.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        _update_debug_usage(chunk, None)


# ===================================================================
# _process_tool_delta
# ===================================================================

class TestProcessToolDelta:
    @pytest.mark.anyio
    async def test_skips_when_no_delta_or_no_tool_calls(self):
        result = list(_process_tool_delta(None, {}, None, None, False))
        assert result == []

    @pytest.mark.anyio
    async def test_skips_when_tool_calls_missing(self):
        delta = MagicMock()
        delta.tool_calls = None
        result = list(_process_tool_delta(delta, {}, None, None, False))
        assert result == []

    @pytest.mark.anyio
    async def test_accumulates_tool_call_arguments(self):
        tc1 = SimpleNamespace(index=0, id="call_1", function=SimpleNamespace(name="get_weather", arguments='{"loc":'))
        tc2 = SimpleNamespace(index=0, id="call_1", function=SimpleNamespace(name="get_weather", arguments='"NYC"}'))
        tool_map = {}
        list(_process_tool_delta(_make_delta(tool_calls=[tc1]), tool_map, None, None, False))
        list(_process_tool_delta(_make_delta(tool_calls=[tc2]), tool_map, None, None, False))
        assert tool_map[0].id == "call_1"
        assert tool_map[0].function.name == "get_weather"
        assert tool_map[0].function.arguments == '{"loc":"NYC"}'

    @pytest.mark.anyio
    async def test_yields_tagged_when_tagged(self):
        tc = SimpleNamespace(index=0, id="call_1", function=SimpleNamespace(name="get_weather", arguments='{"loc":"NYC"}'))
        tool_map = {}
        result = list(_process_tool_delta(_make_delta(tool_calls=[tc]), tool_map, None, None, True))
        assert len(result) >= 1
        assert result[0][0] == "tool_call"

    @pytest.mark.anyio
    async def test_updates_tool_calls_output(self):
        tc = SimpleNamespace(index=0, id="call_1", function=SimpleNamespace(name="search", arguments="{}"))
        tool_map = {}
        output = []
        list(_process_tool_delta(_make_delta(tool_calls=[tc]), tool_map, None, output, False))
        assert len(output) == 1
        assert output[0].function.name == "search"


# ===================================================================
# _update_system_prompt
# ===================================================================

class TestUpdateSystemPrompt:
    @pytest.mark.anyio
    async def test_replaces_first_message_when_system_and_fn_provided(self):
        messages = [{"role": "system", "content": "Old"}]
        _update_system_prompt(messages, "new-model", lambda m: {"role": "system", "content": f"Using {m}"})
        assert messages[0]["content"] == "Using new-model"

    @pytest.mark.anyio
    async def test_noop_when_build_prompt_fn_is_none(self):
        messages = [{"role": "system", "content": "Old"}]
        _update_system_prompt(messages, "new-model", None)
        assert messages[0]["content"] == "Old"

    @pytest.mark.anyio
    async def test_noop_when_messages_empty(self):
        messages = []
        _update_system_prompt(messages, "new-model", lambda m: {})
        assert messages == []

    @pytest.mark.anyio
    async def test_noop_when_first_message_not_system(self):
        messages = [{"role": "user", "content": "Hi"}]
        _update_system_prompt(messages, "new-model", lambda m: {"role": "system", "content": "New"})
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hi"

    @pytest.mark.anyio
    async def test_noop_when_first_item_not_a_dict(self):
        messages = ["not a dict"]
        _update_system_prompt(messages, "new-model", lambda m: {"role": "system", "content": "New"})
        assert messages[0] == "not a dict"


# ===================================================================
# _resolve_model
# ===================================================================

class TestResolveModel:
    @pytest.mark.anyio
    async def test_returns_default_when_model_is_none(self, mock_models, mock_policy):
        mock_policy.return_value = "default-model"
        mock_models.is_model_failed.return_value = False
        result = _resolve_model([], None)
        assert result == "default-model"

    @pytest.mark.anyio
    async def test_returns_model_when_not_failed(self, mock_models, mock_policy):
        mock_models.is_model_failed.return_value = False
        result = _resolve_model([], "gpt-4")
        assert result == "gpt-4"

    @pytest.mark.anyio
    async def test_switches_when_failed(self, mock_models, mock_policy):
        mock_models.is_model_failed.return_value = True
        mock_models._switch_model.return_value = "fallback"
        messages = [{"role": "system", "content": "Old"}]
        result = _resolve_model(messages, "failed-model", lambda m: {"role": "system", "content": f"Now {m}"})
        assert result == "fallback"
        mock_models._switch_model.assert_called_once_with("failed-model")
        assert messages[0]["content"] == "Now fallback"


# ===================================================================
# chat
# ===================================================================

class TestChat:
    @pytest.mark.anyio
    async def test_returns_choice_on_success(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False
        mock_choice = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.return_value = mock_response

        result = await chat([{"role": "user", "content": "Hi"}])

        assert result is mock_choice
        mock_api_call._api_call.assert_called_once_with(
            model="default", messages=[{"role": "user", "content": "Hi"}]
        )

    @pytest.mark.anyio
    async def test_uses_provided_model(self, mock_models, mock_policy, mock_api_call):
        mock_models.is_model_failed.return_value = False
        mock_choice = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.return_value = mock_response

        await chat([{"role": "user", "content": "Hi"}], model="gpt-4")

        mock_policy.assert_not_called()
        mock_api_call._api_call.assert_called_once_with(
            model="gpt-4", messages=[{"role": "user", "content": "Hi"}]
        )

    @pytest.mark.anyio
    async def test_switches_failed_model_before_call(self, mock_models, mock_policy, mock_api_call):
        mock_models.is_model_failed.return_value = True
        mock_models._switch_model.return_value = "backup"
        mock_choice = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.return_value = mock_response

        messages = [{"role": "system", "content": "Old"}]
        await chat(messages, model="failed-model", build_prompt_fn=lambda m: {"role": "system", "content": f"Now {m}"})

        mock_models._switch_model.assert_called_once_with("failed-model")
        assert messages[0]["content"] == "Now backup"
        mock_api_call._api_call.assert_called_once_with(model="backup", messages=messages)

    @pytest.mark.anyio
    async def test_retries_on_exception(self, mock_models, mock_policy, mock_api_call, mock_retry, mock_failover):
        mock_models.is_model_failed.return_value = False
        mock_retry.return_value = False
        mock_failover.return_value = "backup"
        mock_choice = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.side_effect = [Exception("API error"), mock_response]

        result = await chat([{"role": "user", "content": "Hi"}], model="gpt-4")

        assert result is mock_choice
        assert mock_api_call._api_call.call_count == 2
        mock_failover.assert_called_once_with("gpt-4", refresh=True, error=ANY, breaker=None, rate_store=None, registry=None)

    @pytest.mark.anyio
    async def test_populates_debug(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False
        mock_response = MagicMock()
        mock_response.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        mock_choice = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.return_value = mock_response

        debug = DebugInfo()
        await chat([{"role": "user", "content": "Hi"}], debug=debug)

        assert debug.prompt_tokens == 10
        assert debug.completion_tokens == 20
        assert debug.total_tokens == 30

    @pytest.mark.anyio
    async def test_does_not_update_debug_when_not_dict(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False
        mock_response = MagicMock()
        mock_response.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        mock_choice = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.return_value = mock_response

        await chat([{"role": "user", "content": "Hi"}], debug=None)

    @pytest.mark.anyio
    async def test_populates_debug_on_retry(self, mock_models, mock_policy, mock_api_call, mock_failover):
        mock_models.is_model_failed.return_value = False
        mock_failover.return_value = "backup"
        mock_response = MagicMock()
        mock_response.usage = SimpleNamespace(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        mock_choice = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.side_effect = [Exception("fail"), mock_response]

        debug = DebugInfo()
        await chat([{"role": "user", "content": "Hi"}], model="gpt-4", debug=debug)

        assert debug.prompt_tokens == 5
        assert debug.completion_tokens == 10
        assert debug.total_tokens == 15

    @pytest.mark.anyio
    async def test_updates_system_prompt_on_retry(self, mock_models, mock_policy, mock_api_call, mock_failover):
        mock_models.is_model_failed.return_value = False
        mock_failover.return_value = "backup"
        mock_choice = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.side_effect = [Exception("fail"), mock_response]

        messages = [{"role": "system", "content": "Old"}]
        await chat(messages, model="gpt-4", build_prompt_fn=lambda m: {"role": "system", "content": f"Now {m}"})

        assert messages[0]["content"] == "Now backup"

    @pytest.mark.anyio
    async def test_empty_messages_list(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False
        mock_choice = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_api_call._api_call.return_value = mock_response

        result = await chat([])

        assert result is mock_choice
        mock_api_call._api_call.assert_called_once_with(model="default", messages=[])


# ===================================================================
# _process_chunks
# ===================================================================

class TestProcessChunks:
    @pytest.mark.anyio
    async def test_yields_content_untagged(self):
        chunks = [_make_chunk(_make_delta(content="Hello")),
                  _make_chunk(_make_delta(content=" World"))]
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        items, ret = await _collect(_process_chunks(_AsyncListIterator(chunks), None, None, False, None, stats))
        assert items == ["Hello", " World"]
        assert stats.chunk_count == 2
        assert stats.has_content is True
        assert stats.has_reasoning is False

    @pytest.mark.anyio
    async def test_yields_tagged_content_and_reasoning(self):
        delta = _make_delta(content="Answer", reasoning="Think")
        chunk = _make_chunk(delta)
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        items, ret = await _collect(_process_chunks(_AsyncListIterator([chunk]), None, None, True, None, stats))
        assert ("content", "Answer") in items
        assert ("reasoning", "Think") in items
        assert stats.chunk_count == 1
        assert stats.has_content is True
        assert stats.has_reasoning is True

    @pytest.mark.anyio
    async def test_skips_chunks_without_choices(self):
        chunk = MagicMock()
        chunk.choices = None
        chunk.usage = None
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        items, ret = await _collect(_process_chunks(_AsyncListIterator([chunk]), None, None, False, None, stats))
        assert items == []
        assert stats.chunk_count == 1
        assert stats.has_content is False
        assert stats.has_reasoning is False

    @pytest.mark.anyio
    async def test_appends_reasoning_to_output_list(self):
        delta = _make_delta(reasoning="step 1")
        chunk = _make_chunk(delta)
        reasoning_out = []
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        await _collect(_process_chunks(_AsyncListIterator([chunk]), reasoning_out, None, False, None, stats))
        assert reasoning_out == ["step 1"]

    @pytest.mark.anyio
    async def test_updates_debug(self):
        delta = _make_delta(content="Hi")
        chunk = _make_chunk(delta, usage=SimpleNamespace(prompt_tokens=5, completion_tokens=7, total_tokens=12))
        debug = DebugInfo()
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        await _collect(_process_chunks(_AsyncListIterator([chunk]), None, None, False, debug, stats))
        assert debug.prompt_tokens == 5
        assert debug.completion_tokens == 7
        assert debug.total_tokens == 12

    @pytest.mark.anyio
    async def test_returns_metadata_no_content(self):
        delta = _make_delta()
        chunk = _make_chunk(delta)
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        items, ret = await _collect(_process_chunks(_AsyncListIterator([chunk]), None, None, False, None, stats))
        assert stats.chunk_count == 1
        assert stats.has_content is False
        assert stats.has_reasoning is False

    @pytest.mark.anyio
    async def test_processes_tool_calls_tagged(self):
        tc = SimpleNamespace(
            index=0, id="call_1",
            function=SimpleNamespace(name="get_weather", arguments='{"loc":"NYC"}')
        )
        delta = _make_delta(tool_calls=[tc])
        chunk = _make_chunk(delta)
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        items, ret = await _collect(_process_chunks(_AsyncListIterator([chunk]), None, None, True, None, stats))
        tool_items = [r for r in items if isinstance(r, tuple) and r[0] == "tool_call"]
        assert len(tool_items) >= 1
        assert json.loads(tool_items[0][1])["name"] == "_stream_args"

    @pytest.mark.anyio
    async def test_tracks_has_content_and_has_reasoning(self):
        delta = _make_delta(content="A", reasoning="B")
        chunk = _make_chunk(delta)
        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        items, ret = await _collect(_process_chunks(_AsyncListIterator([chunk]), None, None, False, None, stats))
        assert stats.chunk_count == 1
        assert stats.has_content is True
        assert stats.has_reasoning is True


# ===================================================================
# chat_stream
# ===================================================================

class TestChatStream:
    @pytest.mark.anyio
    async def test_yields_content(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False

        delta = _make_delta(content="Hello")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.return_value = _AsyncListIterator([chunk])

        gen = chat_stream([{"role": "user", "content": "Hi"}])
        results, _ = await _collect(gen)
        assert results == ["Hello"]

    @pytest.mark.anyio
    async def test_yields_tagged(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False

        delta = _make_delta(content="Hi")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.return_value = _AsyncListIterator([chunk])

        gen = chat_stream([{"role": "user", "content": "Hi"}], tagged=True)
        results, _ = await _collect(gen)
        assert ("content", "Hi") in results

    @pytest.mark.anyio
    async def test_calls_api_with_stream_options(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False

        delta = _make_delta(content="Hello")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.return_value = _AsyncListIterator([chunk])

        gen = chat_stream([{"role": "user", "content": "Hi"}])
        await _collect(gen)

        mock_api_call._api_call.assert_called_once_with(
            model="default", messages=[{"role": "user", "content": "Hi"}],
            stream=True, stream_options={"include_usage": True}
        )

    @pytest.mark.anyio
    async def test_resolves_model(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = True
        mock_models._switch_model.return_value = "backup"

        delta = _make_delta(content="OK")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.return_value = _AsyncListIterator([chunk])

        messages = [{"role": "system", "content": "Old"}]
        gen = chat_stream(messages, model="failed", build_prompt_fn=lambda m: {"role": "system", "content": f"Now {m}"})
        await _collect(gen)

        mock_models._switch_model.assert_called_once_with("failed")
        assert messages[0]["content"] == "Now backup"

    @pytest.mark.anyio
    async def test_retries_on_stream_error(self, mock_models, mock_policy, mock_api_call, mock_retry, mock_failover):
        mock_models.is_model_failed.return_value = False
        mock_retry.return_value = False
        mock_failover.return_value = "backup"

        delta = _make_delta(content="Retried")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.side_effect = [Exception("stream fail"), _AsyncListIterator([chunk])]

        gen = chat_stream([{"role": "user", "content": "Hi"}], model="gpt-4")
        results, _ = await _collect(gen)
        assert results == ["Retried"]
        assert mock_api_call._api_call.call_count == 2
        mock_failover.assert_called_once_with("gpt-4", refresh=True, error=ANY, breaker=None, rate_store=None, registry=None)

    @pytest.mark.anyio
    async def test_stream_fallback_updates_system_prompt(self, mock_models, mock_policy, mock_api_call, mock_retry, mock_failover):
        mock_models.is_model_failed.return_value = False
        mock_retry.return_value = False
        mock_failover.return_value = "backup"

        delta = _make_delta(content="Recovered")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.side_effect = [Exception("stream fail"), _AsyncListIterator([chunk])]

        messages = [{"role": "system", "content": "Original"}, {"role": "user", "content": "Hi"}]
        gen = chat_stream(
            messages,
            model="gpt-4",
            build_prompt_fn=lambda m: {"role": "system", "content": f"Now {m}"},
        )
        results, _ = await _collect(gen)

        assert results == ["Recovered"]
        assert messages[0]["content"] == "Now backup"
        assert mock_api_call._api_call.call_count == 2
        mock_failover.assert_called_once_with("gpt-4", refresh=True, error=ANY, breaker=None, rate_store=None, registry=None)

    @pytest.mark.anyio
    async def test_retries_when_stream_fails_while_reading_first_chunk(self, mock_models, mock_policy, mock_api_call, mock_retry, mock_failover):
        mock_models.is_model_failed.return_value = False
        mock_retry.return_value = False
        mock_failover.return_value = "deepseek-v4-flash-free"

        delta = _make_delta(content="Recovered")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.side_effect = [_AsyncErrorIterator(), _AsyncListIterator([chunk])]

        gen = chat_stream([{"role": "user", "content": "Hi"}], model="big-pickle")
        results, _ = await _collect(gen)

        assert results == ["Recovered"]
        assert mock_api_call._api_call.call_count == 2
        mock_failover.assert_called_once_with("big-pickle", refresh=True, error=ANY, breaker=None, rate_store=None, registry=None)

    @pytest.mark.anyio
    async def test_midstream_failure_marks_model_before_checkpoint_recovery(
        self,
        mock_models,
        mock_policy,
        mock_api_call,
        mock_retry,
        mock_failover,
    ):
        mock_models.is_model_failed.return_value = False
        mock_retry.return_value = False
        mock_failover.return_value = "backup"
        chunk = _make_chunk(_make_delta(content="partial"))
        mock_api_call._api_call.return_value = _AsyncPartialThenErrorIterator(chunk)

        gen = chat_stream(
            [{"role": "user", "content": "Hi"}],
            model="unstable-model",
        )
        assert await gen.__anext__() == "partial"
        with pytest.raises(Exception, match="connection lost mid-stream"):
            await gen.__anext__()

        mock_failover.assert_called_once_with(
            "unstable-model",
            refresh=True,
            error=ANY,
            breaker=None,
            rate_store=None,
            registry=None,
        )

    @pytest.mark.anyio
    async def test_updates_debug(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False

        delta = _make_delta(content="Hi")
        chunk = _make_chunk(delta, usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30))
        mock_api_call._api_call.return_value = _AsyncListIterator([chunk])

        debug = DebugInfo()
        gen = chat_stream([{"role": "user", "content": "Hi"}], debug=debug)
        await _collect(gen)
        assert debug.prompt_tokens == 10
        assert debug.completion_tokens == 20
        assert debug.total_tokens == 30

    @pytest.mark.anyio
    async def test_reasoning_output_list(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False

        delta = _make_delta(reasoning="thinking slowly")
        chunk = _make_chunk(delta)
        mock_api_call._api_call.return_value = _AsyncListIterator([chunk])

        reasoning_out = []
        gen = chat_stream([{"role": "user", "content": "Think"}], reasoning_output=reasoning_out)
        await _collect(gen)
        assert reasoning_out == ["thinking slowly"]

    @pytest.mark.anyio
    async def test_tool_calls_output(self, mock_models, mock_policy, mock_api_call):
        mock_policy.return_value = "default"
        mock_models.is_model_failed.return_value = False

        tc = SimpleNamespace(
            index=0, id="call_1",
            function=SimpleNamespace(name="search", arguments='{"q":"test"}')
        )
        delta = _make_delta(tool_calls=[tc])
        chunk = _make_chunk(delta)
        mock_api_call._api_call.return_value = _AsyncListIterator([chunk])

        tool_calls_out = []
        gen = chat_stream([{"role": "user", "content": "Search"}], tool_calls_output=tool_calls_out)
        await _collect(gen)
        assert len(tool_calls_out) == 1
        assert tool_calls_out[0].function.name == "search"
