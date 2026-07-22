import asyncio
import logging
import json
from types import SimpleNamespace
from collections.abc import Callable, AsyncGenerator, Generator
from typing import Any
import anyio
import src.llm.model_state as models
import src.llm.api_call as api_call
from src._types import DebugInfo
from src.llm.failover import _mark_and_refresh
from src.llm.selector import get_default_model
from src.llm.retry import is_rate_limit_error

logger = logging.getLogger(__name__)


async def _await_if_needed(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


def _mark_model_success(model: str, breaker=None, rate_store=None) -> None:
    if rate_store is None:
        from src.llm.rate_limit_state import get_rate_limit_store
        rate_store = get_rate_limit_store()
    if breaker is None:
        from src.llm.circuit_breaker import get_breaker
        breaker = get_breaker()
    rate_store.mark_available(model)
    breaker.record_success(model)


def _update_system_prompt(messages: list[dict[str, Any]], model: str, build_prompt_fn: Callable | None = None) -> None:
    if build_prompt_fn and messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0] = build_prompt_fn(model)


def _resolve_model(messages: list[dict[str, Any]], model: str | None, build_prompt_fn: Callable | None = None, default_model_fn: Callable[[], str] | None = None) -> str:
    if model is None:
        if default_model_fn is None:
            default_model_fn = get_default_model
        model = default_model_fn()
    if models.is_model_failed(model):
        try:
            model = models._switch_model(model)
        except RuntimeError:
            model = models.FALLBACK_MODEL
        _update_system_prompt(messages, model, build_prompt_fn)
    return model


async def _with_fallback(
    model: str,
    messages: list[dict[str, Any]],
    build_prompt_fn: Callable | None,
    fn: Callable[[str], Any],
    breaker=None,
    rate_store=None,
    registry=None,
) -> Any:
    try:
        res = await _await_if_needed(fn(model))
        _mark_model_success(model, breaker=breaker, rate_store=rate_store)
        return res
    except Exception as e:
        logger.warning("Error with model %s: %s. Retrying with model switch...", model, e)
        next_model = _mark_and_refresh(
            model,
            refresh=not is_rate_limit_error(e),
            error=e,
            breaker=breaker,
            rate_store=rate_store,
            registry=registry,
        )
        _update_system_prompt(messages, next_model, build_prompt_fn)
        logger.info("Switching model to: %s", next_model)
        return await _await_if_needed(fn(next_model))


async def _try_stream(
    model: str,
    messages: list[dict[str, Any]],
    build_prompt_fn: Callable | None = None,
    breaker=None,
    rate_store=None,
    registry=None,
    **kwargs: Any,
) -> Any:
    if "stream_options" not in kwargs:
        kwargs["stream_options"] = {"include_usage": True}
    try:
        s = await api_call._api_call(model=model, messages=messages, stream=True, **kwargs)
        logger.info("Stream started successfully with model: %s", model)
        _mark_model_success(model, breaker=breaker, rate_store=rate_store)
        return s
    except Exception as e:
        logger.warning("Error starting stream with model %s: %s. Retrying with switch...", model, e)
        # Log full error chain for debugging
        cause = getattr(e, '__cause__', None) or getattr(e, '__context__', None)
        if cause:
            logger.warning("Caused by: %s: %s", type(cause).__name__, cause)
        model = _mark_and_refresh(
            model,
            refresh=not is_rate_limit_error(e),
            error=e,
            breaker=breaker,
            rate_store=rate_store,
            registry=registry,
        )
        _update_system_prompt(messages, model, build_prompt_fn)
        logger.info("Switching stream to: %s", model)
        return await api_call._api_call(model=model, messages=messages, stream=True, **kwargs)


def _process_tool_delta(delta: Any, tool_map: dict[int, Any], reasoning_output: list[str] | None, tool_calls_output: list[Any] | None, tagged: bool) -> Generator[tuple[str, str], None, None]:
    if not delta or not delta.tool_calls:
        return
    for tc in delta.tool_calls:
        raw_idx = getattr(tc, 'index', None)
        idx = 0 if raw_idx is None else raw_idx
        fn = tc.function if tc.function else None
        logger.debug(
            "LLM_STREAM chunk idx=%r id=%r fn_name=%r fn_args=%r",
            raw_idx, getattr(tc, 'id', None),
            getattr(fn, 'name', None) if fn else None,
            getattr(fn, 'arguments', None) if fn else None
        )
        if idx not in tool_map:
            tool_map[idx] = SimpleNamespace(
                id=tc.id or "",
                function=SimpleNamespace(name="", arguments="")
            )
        if tc.id:
            tool_map[idx].id = tc.id
        if fn:
            if fn.name:
                if not fn.name.startswith('$'):
                    tool_map[idx].function.name = fn.name
                if reasoning_output is not None:
                    reasoning_output.append(f"[llama a {fn.name}]")
            if fn.arguments:
                tool_map[idx].function.arguments += fn.arguments
                if tagged:
                    yield ("tool_call", json.dumps({
                        "name": "_stream_args", "idx": idx,
                        "args": tool_map[idx].function.arguments,
                        "status": "partial"
                    }))
        if tool_calls_output is not None:
            tool_calls_output[:] = [v for _, v in sorted(tool_map.items())]


def _update_debug_usage(chunk: Any, debug: DebugInfo | None) -> None:
    usage = getattr(chunk, 'usage', None)
    if usage and isinstance(debug, DebugInfo):
        debug.prompt_tokens = usage.prompt_tokens
        debug.completion_tokens = usage.completion_tokens
        debug.total_tokens = usage.total_tokens


async def chat(messages: list[dict[str, Any]], model: str | None = None, build_prompt_fn: Callable | None = None, breaker=None, rate_store=None, registry=None, default_model_fn: Callable[[], str] | None = None, **kwargs: Any) -> Any:
    debug = kwargs.pop("debug", None)
    if model is None:
        if default_model_fn is None:
            default_model_fn = get_default_model
        model = default_model_fn()
    if models.is_model_failed(model):
        try:
            model = models._switch_model(model)
        except RuntimeError:
            model = models.FALLBACK_MODEL
        _update_system_prompt(messages, model, build_prompt_fn)

    from src.llm.protocol import UnifiedResponse

    async def _call(m: str) -> Any:
        response = await api_call._api_call(model=m, messages=messages, **kwargs)
        _update_debug_usage(response, debug)
        if isinstance(response, UnifiedResponse):
            tool_calls = None
            if response.tool_calls:
                tool_calls = [
                    SimpleNamespace(
                        id=tc.id,
                        type="function",
                        function=SimpleNamespace(name=tc.name, arguments=tc.arguments)
                    )
                    for tc in response.tool_calls
                ]
            message = SimpleNamespace(
                role="assistant",
                content=response.content,
                reasoning_content=response.reasoning,
                tool_calls=tool_calls
            )
            return SimpleNamespace(
                message=message,
                finish_reason=response.finish_reason
            )
        return response.choices[0]

    return await _with_fallback(model, messages, build_prompt_fn, _call, breaker=breaker, rate_store=rate_store, registry=registry)



async def _iter_with_timeout(stream: Any, timeout: float = 30.0) -> AsyncGenerator[Any, None]:
    while True:
        try:
            with anyio.fail_after(timeout):
                chunk = await stream.__anext__()
            yield chunk
        except StopAsyncIteration:
            break


async def _process_chunks(
    stream: Any,
    reasoning_output: list[str] | None,
    tool_calls_output: list[Any] | None,
    tagged: bool,
    debug: DebugInfo | None,
    stats: SimpleNamespace
) -> AsyncGenerator[Any, None]:
    _tool_map: dict[int, Any] = {}
    stats.chunk_count = 0
    stats.has_content = False
    stats.has_reasoning = False

    async for chunk in _iter_with_timeout(stream):
        stats.chunk_count += 1

        if isinstance(chunk, tuple) and len(chunk) == 2 and isinstance(chunk[0], str):
            event_type, payload = chunk
            if event_type == "usage":
                if isinstance(debug, DebugInfo) and payload:
                    debug.prompt_tokens = payload.prompt_tokens
                    debug.completion_tokens = payload.completion_tokens
                    debug.total_tokens = payload.total_tokens

            elif event_type == "reasoning":
                stats.has_reasoning = True
                if reasoning_output is not None:
                    reasoning_output.append(payload)
                if tagged:
                    yield ("reasoning", payload)

            elif event_type == "content":
                stats.has_content = True
                if tagged:
                    yield ("content", payload)
                else:
                    yield payload

            elif event_type == "tool_call":
                delta = payload
                idx = delta.index
                if idx not in _tool_map:
                    _tool_map[idx] = SimpleNamespace(
                        id=delta.id or "",
                        function=SimpleNamespace(name="", arguments="")
                    )
                if delta.id:
                    _tool_map[idx].id = delta.id
                if delta.name:
                    _tool_map[idx].function.name = delta.name
                if delta.arguments:
                    _tool_map[idx].function.arguments += delta.arguments
                if tool_calls_output is not None:
                    tool_calls_output[:] = [v for _, v in sorted(_tool_map.items())]
                if tagged:
                    yield ("tool_call", json.dumps({
                        "name": "_stream_args", "idx": idx,
                        "args": _tool_map[idx].function.arguments,
                        "status": "partial"
                    }))
        else:
            # Legacy raw OpenAI chunk object
            _update_debug_usage(chunk, debug)

            if not getattr(chunk, 'choices', None):
                logger.debug("Chunk %d sin choices", stats.chunk_count)
                continue

            delta = chunk.choices[0].delta
            r = getattr(delta, 'reasoning_content', None) or getattr(delta, 'reasoning', None) if delta else None
            if r:
                stats.has_reasoning = True
                if reasoning_output is not None:
                    reasoning_output.append(r)
                if tagged:
                    yield ("reasoning", r)

            for item in _process_tool_delta(delta, _tool_map, reasoning_output, tool_calls_output, tagged):
                yield item

            content = delta.content if delta else None
            if content:
                stats.has_content = True
                if tagged:
                    yield ("content", content)
                else:
                    yield content


async def chat_stream(
    messages: list[dict[str, Any]],
    model: str | None = None,
    build_prompt_fn: Callable | None = None,
    reasoning_output: list[str] | None = None,
    tagged: bool = False,
    tool_calls_output: list[Any] | None = None,
    breaker=None,
    rate_store=None,
    registry=None,
    default_model_fn: Callable[[], str] | None = None,
    **kwargs: Any
) -> AsyncGenerator[Any, None]:
    debug = kwargs.pop("debug", None)
    model = _resolve_model(messages, model, build_prompt_fn, default_model_fn=default_model_fn)
    retried_after_read_error = False

    while True:
        stream = await _try_stream(model, messages, build_prompt_fn, breaker=breaker, rate_store=rate_store, registry=registry, **kwargs)

        stats = SimpleNamespace(chunk_count=0, has_content=False, has_reasoning=False)
        try:
            async for item in _process_chunks(
                stream, reasoning_output, tool_calls_output, tagged, debug, stats
            ):
                yield item
        except Exception as e:
            if stats.has_content or stats.has_reasoning:
                _mark_and_refresh(
                    model,
                    refresh=not is_rate_limit_error(e),
                    error=e,
                    breaker=breaker,
                    rate_store=rate_store,
                    registry=registry,
                )
                raise
            if retried_after_read_error:
                raise
            retried_after_read_error = True
            next_model = _mark_and_refresh(
                model,
                refresh=not is_rate_limit_error(e),
                error=e,
                breaker=breaker,
                rate_store=rate_store,
                registry=registry,
            )
            if next_model == model:
                raise
            _update_system_prompt(messages, next_model, build_prompt_fn)
            logger.info("Switching stream after read error to: %s", next_model)
            model = next_model
            continue

        if stats.chunk_count == 0:
            logger.warning("Empty stream: no chunks received from model %s", model)
        elif not stats.has_content and not stats.has_reasoning:
            logger.warning("Stream with %d chunks but no content or reasoning from model %s", stats.chunk_count, model)
        else:
            logger.info("Stream completed: %d chunks, has_content=%s, has_reasoning=%s", stats.chunk_count, stats.has_content, stats.has_reasoning)
        return
