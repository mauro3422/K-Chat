import logging
import json
from types import SimpleNamespace
from typing import Generator
from src.llm import models, manager

logger = logging.getLogger(__name__)

def chat(messages: list, model: str = None, **kwargs):
    debug = kwargs.pop("debug", None)
    if model is None:
        model = manager.get_default_model()
    if model in models._failed_models:
        model = models._switch_model(model)
        models._update_system_prompt(messages, model)
    try:
        response = models._api_call(
            model=model,
            messages=messages,
            **kwargs
        )
        if response and isinstance(debug, dict) and getattr(response, "usage", None):
            debug["prompt_tokens"] = response.usage.prompt_tokens
            debug["completion_tokens"] = response.usage.completion_tokens
            debug["total_tokens"] = response.usage.total_tokens
        return response.choices[0]
    except Exception as e:
        logger.warning("Error con modelo %s: %s. Reintentando con switch de modelo...", model, e)
        next_model = manager._mark_and_refresh(model)
        models._update_system_prompt(messages, next_model)
        logger.info("Realizando switch de modelo a: %s", next_model)
        response = models._api_call(
            model=next_model,
            messages=messages,
            **kwargs
        )
        if response and isinstance(debug, dict) and getattr(response, "usage", None):
            debug["prompt_tokens"] = response.usage.prompt_tokens
            debug["completion_tokens"] = response.usage.completion_tokens
            debug["total_tokens"] = response.usage.total_tokens
        return response.choices[0]

def chat_stream(messages: list, model: str = None, reasoning_output: list = None, tagged: bool = False, tool_calls_output: list = None, **kwargs) -> Generator:
    """Igual que chat() pero devuelve tokens de a uno (generator)."""
    debug = kwargs.pop("debug", None)
    if model is None:
        model = manager.get_default_model()
    if model in models._failed_models:
        model = models._switch_model(model)
        models._update_system_prompt(messages, model)

    if "stream_options" not in kwargs:
        kwargs["stream_options"] = {"include_usage": True}

    logger.info("Iniciando stream con modelo: %s", model)
    
    try:
        stream = models._api_call(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
        logger.info("Stream iniciado correctamente con modelo: %s", model)
    except Exception as e:
        logger.warning("Error iniciando stream con modelo %s: %s. Reintentando con switch...", model, e)
        model = manager._mark_and_refresh(model)
        models._update_system_prompt(messages, model)
        logger.info("Realizando switch de stream a: %s", model)
        stream = models._api_call(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )

    _tool_map = {}
    chunk_count = 0
    has_content = False
    has_reasoning = False

    for chunk in stream:
        chunk_count += 1
        usage = getattr(chunk, 'usage', None)
        if usage and isinstance(debug, dict):
            debug["prompt_tokens"] = usage.prompt_tokens
            debug["completion_tokens"] = usage.completion_tokens
            debug["total_tokens"] = usage.total_tokens

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
        
        if delta and delta.tool_calls:
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

                if idx not in _tool_map:
                    _tool_map[idx] = SimpleNamespace(
                        id=tc.id or "",
                        function=SimpleNamespace(name="", arguments="")
                    )

                if tc.id:
                    _tool_map[idx].id = tc.id

                if fn:
                    if fn.name:
                        if not fn.name.startswith('$'):
                            _tool_map[idx].function.name = fn.name
                        if reasoning_output is not None:
                            reasoning_output.append(f"[llama a {fn.name}]")
                    if fn.arguments:
                        _tool_map[idx].function.arguments += fn.arguments
                        if tagged:
                            yield ("tool_call", json.dumps({
                                "name": "_stream_args",
                                "idx": idx,
                                "args": _tool_map[idx].function.arguments,
                                "status": "partial"
                            }))

                if tool_calls_output is not None:
                    tool_calls_output[:] = [v for _, v in sorted(_tool_map.items())]

        content = delta.content if delta else None
        if content:
            has_content = True
            if tagged:
                yield ("content", content)
            else:
                yield content

    if chunk_count == 0:
        logger.warning("Stream vacío: no se recibieron chunks del modelo %s", model)
    elif not has_content and not has_reasoning:
        logger.warning("Stream con %d chunks pero sin contenido ni reasoning del modelo %s", chunk_count, model)
    else:
        logger.info("Stream completado: %d chunks, has_content=%s, has_reasoning=%s", chunk_count, has_content, has_reasoning)
