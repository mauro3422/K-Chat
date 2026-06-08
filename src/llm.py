import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Generator

from openai import OpenAI
from config import OPENCODE_ZEN_API_KEY
from src.context import build_system_prompt

logger = logging.getLogger(__name__)

_MAX_RETRIES = 1
_RETRY_DELAY = 0.5


def _api_call(**kwargs):
    """Wrapper con retry exponencial sobre client.chat.completions.create."""
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.debug("Retry %d/%d para %s en %.1fs: %s", attempt + 1, _MAX_RETRIES, kwargs.get("model"), delay, e)
                time.sleep(delay)
    raise last_error

client = OpenAI(
    api_key=OPENCODE_ZEN_API_KEY,
    base_url="https://opencode.ai/zen/v1"
)

PRIORITY = ["big-pickle", "deepseek-v4-flash-free"]
FALLBACK_MODEL = "deepseek-v4-flash-free"

_cached_models = None
_failed_models = set()
_verified_models = None


def _switch_model(model: str) -> str:
    """Devuelve el modelo alternativo cuando el actual falló."""
    return FALLBACK_MODEL if model != FALLBACK_MODEL else "big-pickle"


def _update_system_prompt(messages: list, model: str) -> None:
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0] = build_system_prompt(model)


def _mark_and_refresh(model: str) -> str:
    """Marca modelo como fallido, refresca lista verificada y devuelve el modelo alternativo."""
    try:
        get_verified_models(force_refresh=True)
    except Exception:
        pass
    _failed_models.add(model)
    next_model = _switch_model(model)
    return next_model


def verify_model(model_id: str) -> bool:
    """Prueba si un modelo responde correctamente enviando un mensaje ultracorto."""
    try:
        _api_call(
            model=model_id,
            messages=[{"role": "user", "content": "hola"}],
            max_tokens=2,
            timeout=2.0
        )
        return True
    except Exception as e:
        logger.warning("Modelo %s no pasó la verificación: %s", model_id, e)
        return False


def get_verified_models(force_refresh: bool = False) -> list:
    """Devuelve la lista de modelos gratuitos que están activos y funcionando."""
    global _verified_models
    if _verified_models is None or force_refresh:
        try:
            free_models = get_free_models(force_refresh=force_refresh)
            verified = []

            def check(model_id: str):
                if verify_model(model_id):
                    return model_id
                return None

            with ThreadPoolExecutor(max_workers=max(1, len(free_models))) as executor:
                results = executor.map(check, [m.id for m in free_models])
                for res in results:
                    if res:
                        verified.append(res)
            _verified_models = verified
        except Exception as e:
            logger.error("Error verificando modelos: %s", e)
            if _verified_models is not None:
                return _verified_models
            _verified_models = [FALLBACK_MODEL]
    return _verified_models


def get_models(force_refresh: bool = False):
    """Devuelve todos los modelos disponibles desde la API (con caché en memoria)."""
    global _cached_models
    if _cached_models is None or force_refresh:
        try:
            _cached_models = list(client.models.list())
        except Exception as e:
            logger.error("Error al obtener modelos de la API: %s", e)
            if _cached_models is not None:
                return _cached_models
            raise e
    return _cached_models


def get_free_models(force_refresh: bool = False):
    """Devuelve solo los modelos gratuitos (IDs que terminan en -free)."""
    all_models = get_models(force_refresh=force_refresh)
    return [model for model in all_models if model.id.endswith("-free")]


def get_paid_models(force_refresh: bool = False):
    """Devuelve los modelos de pago."""
    all_models = get_models(force_refresh=force_refresh)
    return [model for model in all_models if not model.id.endswith("-free")]


def get_default_model():
    """Elige el primer modelo de PRIORITY que esté disponible y no haya fallado. Si la API no responde, usa el fallback."""
    try:
        free_ids = [m.id for m in get_free_models()]
        for modelo in PRIORITY:
            if modelo not in _failed_models:
                if modelo in free_ids or modelo == "big-pickle":
                    return modelo
    except Exception as e:
        logger.warning("Error obteniendo modelos: %s", e)
    return FALLBACK_MODEL


def chat(messages: list, model: str = None, **kwargs):
    debug = kwargs.pop("debug", None)
    if model is None:
        model = get_default_model()
    if model in _failed_models:
        model = _switch_model(model)
        _update_system_prompt(messages, model)
    try:
        response = _api_call(
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
        next_model = _mark_and_refresh(model)
        _update_system_prompt(messages, next_model)
        logger.info("Realizando switch de modelo a: %s", next_model)
        response = _api_call(
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
    """Igual que chat() pero devuelve tokens de a uno (generator).
       Si reasoning_output se pasa (lista mutable), se llena con tokens de razonamiento.
       Si tool_calls_output se pasa (lista mutable), se llena con objetos SimpleNamespace
       con .id, .function.name, .function.arguments extraídos del stream (sin sync fallback).
       Si tagged=True, yield (tipo, token): ("reasoning", text) o ("content", text).
       kwargs se pasan a create(), ej: tools=TOOLS."""
    debug = kwargs.pop("debug", None)
    if model is None:
        model = get_default_model()
    if model in _failed_models:
        model = _switch_model(model)
        _update_system_prompt(messages, model)

    if "stream_options" not in kwargs:
        kwargs["stream_options"] = {"include_usage": True}

    logger.info("Iniciando stream con modelo: %s", model)
    
    try:
        stream = _api_call(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
        logger.info("Stream iniciado correctamente con modelo: %s", model)
    except Exception as e:
        logger.warning("Error iniciando stream con modelo %s: %s. Reintentando con switch...", model, e)
        model = _mark_and_refresh(model)
        _update_system_prompt(messages, model)
        logger.info("Realizando switch de stream a: %s", model)
        stream = _api_call(
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
        # Extraer tokens si vienen en el chunk
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

                # Inicializar slot para este índice si es la primera vez
                if idx not in _tool_map:
                    _tool_map[idx] = SimpleNamespace(
                        id=tc.id or "",
                        function=SimpleNamespace(name="", arguments="")
                    )

                # Actualizar id si llega explícito
                if tc.id:
                    _tool_map[idx].id = tc.id

                if fn:
                    # El primer chunk trae el nombre; chunks posteriores traen args
                    if fn.name:
                        # Ignorar nombres que son placeholders del razonamiento del modelo
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

    # Log final del stream
    if chunk_count == 0:
        logger.warning("Stream vacío: no se recibieron chunks del modelo %s", model)
    elif not has_content and not has_reasoning:
        logger.warning("Stream con %d chunks pero sin contenido ni reasoning del modelo %s", chunk_count, model)
    else:
        logger.info("Stream completado: %d chunks, has_content=%s, has_reasoning=%s", chunk_count, has_content, has_reasoning)
