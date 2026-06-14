> ⚠️ This document may lag behind the current version. See [docs/ARCHITECTURE.md](ARCHITECTURE.md) and [docs/MODULES.md](MODULES.md) for the latest.
>
> **Last updated:** 2026-06-14 — Updated deps: providers.py/discovery.py/retry.py now depend on config_loader for `config` param DI; all accept optional `config` parameter.

# Arquitectura de `src/llm/`

## 1. Qué hace cada archivo

| Archivo | Función |
|---|---|---|
| `__init__.py` | Package marker only |
| `protocol.py` | Define `LLMProvider` Protocol (interfaz con `chat`, `chat_stream`, `list_models`) |
| `adapters/openai_adapter.py` | Implementación concreta de `LLMProvider` usando el SDK de OpenAI |
| `providers.py` | Registro de providers (dict nombre→clase) + singleton lazy `_get_provider()`, acepta `config` param opcional para DI |
| `model_state.py` | Estado thread-safe: modelos fallidos, verificados, caché de modelos. Lógica de fallback por prioridad con `_switch_model()`. |
| `api_call.py` | Wrapper `_api_call()` con backoff exponencial |
| `discovery.py` | `get_models()` — consulta modelos disponibles del provider, filtra free models |
| `verifier.py` | `verify_model()` — prueba si un modelo responde correctamente con un chat minimal |
| `selector.py` | `get_default_model()` — elige modelo según prioridad, fallback, y estado de fallos |
| `failover.py` | `_mark_and_refresh()` — marca modelo como fallido, refresca lista verificada |
| `retry.py` | `execute_with_retry()` — lógica genérica de rate-limit retry con backoff exponencial, desacoplada de `api_call.py` |
| `client.py` | Puntos de entrada `chat()` y `chat_stream()`: resolución de modelo, failover, streaming, procesamiento de tool calls |

## 2. Provider Pattern

```
protocol.py (Protocol)
    └── LLMProvider: chat(), chat_stream(), list_models()

providers.py (Registry)
    ├── _PROVIDER_REGISTRY: dict[str, type[LLMProvider]]
    ├── register_provider("openai", OpenAIAdapter)  ← se registra al importar
    └── _get_provider() → singleton lazy, lee LLM_PROVIDER env
```

## 3. Failover

Flujo cuando un modelo falla:

```
client._with_fallback()
  → exception → failover._mark_and_refresh(model)
    → model_state.mark_model_failed(model)        # agrega a _failed_models
    → discovery.get_verified_models(force=True)    # re-verifica todos los free models
    → model_state._switch_model(model)             # busca siguiente en PRIORITY que no esté en _failed_models
  → reintentar con next_model
```

`_switch_model` en `model_state.py`:
- Si el modelo actual es `FALLBACK_MODEL`, busca el primero de `PRIORITY` que no haya fallado.
- Si no, retorna `FALLBACK_MODEL`.

Stream tiene su propio fallback en `_try_stream()` con la misma lógica.

## 4. Dependencias

```
__init__.py ──→ (package marker only)
protocol.py ──→ (ninguna)
adapters/openai_adapter.py ──→ openai, config
providers.py ──→ protocol, adapters, config_loader
model_state.py ──→ (ninguna, solo stdlib)
api_call.py ──→ providers, retry
discovery.py ──→ model_state, adapters, config_loader
verifier.py ──→ adapters
selector.py ──→ model_state
failover.py ──→ model_state, discovery
retry.py ──→ config_loader, stdlib + time
client.py ──→ api_call, model_state, discovery, failover, selector, retry
```

## 5. Lo que está bien

## 5. Lo que está bien

- **Protocol checkable**: `LLMProvider` usa `@runtime_checkable`, permite `isinstance()` en runtime.
- **Thread safety**: `model_state.py` usa `threading.Lock` para todo acceso a estado compartido.
- **Separación clara**: protocol → implementación → registro → estado → manager → client.
- **Failover automático**: el cliente cambia de modelo sin que el caller lo note.
- **Re-verificación paralela**: `get_verified_models` usa `ThreadPoolExecutor` para probar modelos concurrentemente.
- **Backoff exponencial**: `_api_call` reintenta con delay creciente.

## 6. Lo que podría mejorar

- **`api_call.py` concentra la llamada al proveedor** y `model_state.py` concentra el estado compartido.
- **`_switch_model` confusa**: cuando `model != FALLBACK_MODEL` siempre retorna `FALLBACK_MODEL`, sin importar la prioridad. La lógica de "buscar en PRIORITY" solo aplica si ya estás en el fallback.
- **`_MAX_RETRIES = 1`**: en la práctica solo hace 1 intento (0 reintentos reales). El backoff exponencial no se aprovecha.
- **Duplicación de lógica de failover**: `_try_stream()` y `_with_fallback()` repaten el mismo patrón de catch→mark→switch→retry.
- **`get_default_model` hardcodea `"big-pickle"`**: línea 75 tiene un `or modelo == "big-pickle"` que parece un hack para permitir un modelo no-free.
- **Sin invalidación de caché por tiempo**: `_cached_models` y `_verified_models` solo se refrescan por `force_refresh`, nunca por TTL.
- **Se puede afinar aún más la separación** entre `discovery`, `selector` y `failover`, pero ya no hay facades de compatibilidad.
- **Stream fallback y prompt**: ya quedó corregido para que `chat_stream()` también reescriba el system prompt cuando cambia de modelo.
