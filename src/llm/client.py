import logging
import json
from types import SimpleNamespace
from collections.abc import Callable, Generator
from typing import Any
import src.llm.model_state as models
import src.llm.api_call as api_call
from src.core.debug_info import DebugInfo
from src.llm.failover import _mark_and_refresh
from src.llm.selector import get_default_model
from src.llm.retry import is_rate_limit_error

logger = logging.getLogger(__name__)


def _update_system_prompt(messages: list[dict[str, Any]], model: str, build_prompt_fn: Callable | None = None) -> None:
    if build_prompt_fn and messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0] = build_prompt_fn(model)


def _resolve_model(messages: list[dict[str, Any]], model: str | None, build_prompt_fn: Callable | None = None) -> str:
    if model is None:
        model = get_default_model()
    if models.is_model_failed(model):
        model = models._switch_model(model)
        _update_system_prompt(messages, model, build_prompt_fn)
    return model


def _extract_debug_usage(response: Any, debug: DebugInfo | None) -> None:
    if response and isinstance(debug, DebugInfo) and getattr(response, "usage", None):
        debug.prompt_tokens = response.usage.prompt_tokens
        debug.completion_tokens = response.usage.completion_tokens
        debug.total_tokens = response.usage.total_tokens


def _with_fallback(
    model: str,
    messages: list[dict[str, Any]],
    build_prompt_fn: Callable | None,
    fn: Callable[[str], Any],
) -> Any:
    try:
        return fn(model)
    except Exception as e:
        logger.warning("Error with model %s: %s. Retrying with model switch...", model, e)
        next_model = _mark_and_refresh(model, refresh=not is_rate_limit_error(e))
        _update_system_prompt(messages, next_model, build_prompt_fn)
        logger.info("Switching model to: %s", next_model)
        return fn(next_model)


def _try_stream(
    model: str,
    messages: list[dict[str, Any]],
    build_prompt_fn: Callable | None = None,
    **kwargs: Any,
) -> Any:
    if "stream_options" not in kwargs:
        kwargs["stream_options"] = {"include_usage": True}
    try:
        s = api_call._api_call(model=model, messages=messages, stream=True, **kwargs)
        logger.info("Stream started successfully with model: %s", model)
        return s
    except Exception as e:
        logger.warning("Error starting stream with model %s: %s. Retrying with switch...", model, e)
        model = _mark_and_refresh(model, refresh=not is_rate_limit_error(e))
        _update_system_prompt(messages, model, build_prompt_fn)
        logger.info("Switching stream to: %s", model)
        return api_call._api_call(model=model, messages=messages, stream=True, **kwargs)


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


def chat(messages: list[dict[str, Any]], model: str | None = None, build_prompt_fn: Callable | None = None, **kwargs: Any) -> Any:
    debug = kwargs.pop("debug", None)
    if model is None:
        model = get_default_model()
    if models.is_model_failed(model):
        model = models._switch_model(model)
        _update_system_prompt(messages, model, build_prompt_fn)

    def _call(m: str) -> Any:
        response = api_call._api_call(model=m, messages=messages, **kwargs)
        _extract_debug_usage(response, debug)
        return response.choices[0]

    return _with_fallback(model, messages, build_prompt_fn, _call)


def _process_chunks(
    stream: Any,
    reasoning_output: list[str] | None,
    tool_calls_output: list[Any] | None,
    tagged: bool,
    debug: DebugInfo | None,
) -> Generator[Any, None, tuple[int, bool, bool]]:
    _tool_map: dict[int, Any] = {}
    chunk_count = 0
    has_content = False
    has_reasoning = False

    for chunk in stream:
        chunk_count += 1
        _update_debug_usage(chunk, debug)

        if not getattr(chunk, 'choices', None):
            logger.debug("Chunk %d sin choices", chunk_count)
            continue

        delta = chunk.choices[0].delta
        r = getattr(delta, 'reasoning_content', None) or getattr(delta, 'reasoning', None) if delta else None
        if r:
            has_reasoning = True
            if reasoning_output is not None:
                reasoning_output.append(r)
            if tagged:
                yield ("reasoning", r)

        yield from _process_tool_delta(delta, _tool_map, reasoning_output, tool_calls_output, tagged)

        content = delta.content if delta else None
        if content:
            has_content = True
            if tagged:
                yield ("content", content)
            else:
                yield content

    return chunk_count, has_content, has_reasoning


def chat_stream(
    messages: list[dict[str, Any]],
    model: str | None = None,
    build_prompt_fn: Callable | None = None,
    reasoning_output: list[str] | None = None,
    tagged: bool = False,
    tool_calls_output: list[Any] | None = None,
    **kwargs: Any
) -> Generator[Any, None, None]:
    debug = kwargs.pop("debug", None)
    model = _resolve_model(messages, model, build_prompt_fn)
    stream = _try_stream(model, messages, build_prompt_fn, **kwargs)

    chunk_count, has_content, has_reasoning = yield from _process_chunks(
        stream, reasoning_output, tool_calls_output, tagged, debug,
    )

    if chunk_count == 0:
        logger.warning("Empty stream: no chunks received from model %s", model)
    elif not has_content and not has_reasoning:
        logger.warning("Stream with %d chunks but no content or reasoning from model %s", chunk_count, model)
    else:
        logger.info("Stream completed: %d chunks, has_content=%s, has_reasoning=%s", chunk_count, has_content, has_reasoning)
