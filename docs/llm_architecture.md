# Arquitectura de `src/llm/`

## 1. Qué hace cada archivo

| Archivo | Función |
|---|---|
| `__init__.py` | Package marker only |
| `protocol.py` | Define `LLMProvider` Protocol (interfaz con `chat`, `chat_stream`, `list_models`) |
| `openai_provider.py` | Implementación concreta de `LLMProvider` usando el SDK de OpenAI |
| `providers.py` | Registro de providers (dict nombre→clase) + singleton lazy `_get_provider()` |
| `model_state.py` | Estado thread-safe: modelos fallidos, verificados, caché de modelos. Lógica de fallback por prioridad |
| `models.py` | Re-exporta de `providers` y `model_state`. Wrapper `_api_call()` con backoff exponencial |
| `policy.py` | Lógica de negocio: verificación de modelos (async), selección por prioridad, refresh de lista verificada |
| `client.py` | Puntos de entrada `chat()` y `chat_stream()`: resolución de modelo, failover, streaming, procesamiento de tool calls |

## 2. Provider Pattern

```
protocol.py (Protocol)
    └── LLMProvider: chat(), chat_stream(), list_models()

providers.py (Registry)
    ├── _PROVIDER_REGISTRY: dict[str, type[LLMProvider]]
    ├── register_provider("openai", OpenAIProvider)  ← se registra al importar
    └── _get_provider() → singleton lazy, lee LLM_PROVIDER env
```

- El registro es un dict global. `register_provider` agrega clases.
- `_get_provider()` usa `os.environ.get("LLM_PROVIDER", "openai")` para elegir la clase, luego la instancia una vez.
- Para agregar un provider nuevo: crear clase con la interfaz, llamar `register_provider("nombre", MiClase)`.

## 3. Failover

Flujo cuando un modelo falla:

```
client._with_fallback()
  → exception → policy._mark_and_refresh(model)
    → mark_model_failed(model)        # agrega a _failed_models
    → get_verified_models(force=True)  # re-verifica todos los free models
    → _switch_model(model)             # busca siguiente en PRIORITY que no esté en _failed_models
  → reintentar con next_model
```

`_switch_model` en `model_state.py:55`:
- Si el modelo actual es `FALLBACK_MODEL`, busca el primero de `PRIORITY` que no haya fallado.
- Si no, retorna `FALLBACK_MODEL`.

Stream tiene su propio fallback en `_try_stream()` con la misma lógica.

## 4. Dependencias

```
__init__.py ──→ (package marker only)
protocol.py ──→ (ninguna)
openai_provider.py ──→ openai, config
providers.py ──→ protocol, openai_provider
model_state.py ──→ (ninguna, solo stdlib)
models.py ──→ providers, model_state
policy.py ──→ models
client.py ──→ models, policy
```

## 5. Lo que está bien

- **Protocol checkable**: `LLMProvider` usa `@runtime_checkable`, permite `isinstance()` en runtime.
- **Thread safety**: `model_state.py` usa `threading.Lock` para todo acceso a estado compartido.
- **Separación clara**: protocol → implementación → registro → estado → manager → client.
- **Failover automático**: el cliente cambia de modelo sin que el caller lo note.
- **Re-verificación paralela**: `get_verified_models` usa `ThreadPoolExecutor` para probar modelos concurrentemente.
- **Backoff exponencial**: `_api_call` reintenta con delay creciente.

## 6. Lo que podría mejorar

- **`models.py` rompe encapsulación**: expone `_get_provider()` y `_api_call()` como semipúblicos. `policy.py` y `client.py` acceden a internals de otros módulos.
- **`_switch_model` confusa**: cuando `model != FALLBACK_MODEL` siempre retorna `FALLBACK_MODEL`, sin importar la prioridad. La lógica de "buscar en PRIORITY" solo aplica si ya estás en el fallback.
- **`_MAX_RETRIES = 1`**: en la práctica solo hace 1 intento (0 reintentos reales). El backoff exponencial no se aprovecha.
- **Duplicación de lógica de failover**: `_try_stream()` y `_with_fallback()` repaten el mismo patrón de catch→mark→switch→retry.
- **`get_default_model` hardcodea `"big-pickle"`**: línea 75 tiene un `or modelo == "big-pickle"` que parece un hack para permitir un modelo no-free.
- **Sin invalidación de caché por tiempo**: `_cached_models` y `_verified_models` solo se refrescan por `force_refresh`, nunca por TTL.
- **`wildcard imports`** en `models.py`: `from providers import *` y `from model_state import *` dificultan rastrear qué símbolos están disponibles.
