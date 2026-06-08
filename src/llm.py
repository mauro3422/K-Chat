import json
import logging
from openai import OpenAI
from config import OPENCODE_ZEN_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=OPENCODE_ZEN_API_KEY,
    base_url="https://opencode.ai/zen/v1"
)

PRIORITY = ["big-pickle", "deepseek-v4-flash-free"]
FALLBACK_MODEL = "deepseek-v4-flash-free"

_cached_models = None

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
    """Elige el primer modelo de PRIORITY que esté disponible. Si la API no responde, usa el fallback."""
    try:
        free_ids = [m.id for m in get_free_models()]
        for modelo in PRIORITY:
            if modelo in free_ids or modelo == "big-pickle":
                return modelo
    except Exception as e:
        logger.warning("Error obteniendo modelos: %s", e)
    return FALLBACK_MODEL

# --- Script de verificación de modelos (correr manualmente para actualizar lista) --- (MODIFICAR)
# from src.llm import get_free_models, chat
# free = get_free_models()
# for m in free:
#     try:
#         r = chat('Decime solo tu nombre en una palabra', model=m.id)
#         print(f'  {m.id:35s} -> {r}')
#     except Exception as e:
#         print(f'  {m.id:35s} -> ERROR: {str(e)[:60]}')
# También probar modelos sin -free que nos interesen:
# chat('hola', model='big-pickle')

def chat(messages: list, model: str = None, **kwargs):
    if model is None:
        model = get_default_model()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs
    )
    return response.choices[0]

def chat_stream(messages: list, model: str = None, reasoning_output: list = None, tagged: bool = False, **kwargs):
    """Igual que chat() pero devuelve tokens de a uno (generator).
       Si reasoning_output se pasa (lista mutable), se llena con tokens de razonamiento.
       Si tagged=True, yield (tipo, token): ("reasoning", text) o ("content", text).
       kwargs se pasan a create(), ej: tools=TOOLS."""
    if model is None:
        model = get_default_model()
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        **kwargs
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        r = getattr(delta, 'reasoning_content', None) or getattr(delta, 'reasoning', None) if delta else None
        if r:
            if reasoning_output is not None:
                reasoning_output.append(r)
            if tagged:
                yield ("reasoning", r)
        tcs = getattr(delta, 'tool_calls', None)
        if tcs:
            for tc in tcs:
                if tc.function and tc.function.name:
                    if tagged:
                        yield ("tool_call", json.dumps({"name": tc.function.name, "args": {}, "status": "calling"}))
                    if reasoning_output is not None:
                        reasoning_output.append(f"[llama a {tc.function.name}]")
                elif tc.function and tc.function.arguments:
                    if tagged:
                        yield ("tool_call", json.dumps({"name": "_stream_args", "args": tc.function.arguments, "status": "partial"}))
        content = delta.content
        if content:
            if tagged:
                yield ("content", content)
            else:
                yield content
