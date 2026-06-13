# Auditoría de `src/llm/`

## 1. Qué cubre

Este bloque concentra:
- selección de modelo por prioridad
- estado compartido de modelos fallidos/verificados
- discovery de modelos disponibles
- verificación de modelos
- failover
- retry por rate limit
- chat y chat_stream con procesamiento de tool calls

## 2. Corte de responsabilidades actual

- [`src/llm/model_state.py`](/home/maurol/dev/K-Chat/src/llm/model_state.py) guarda el estado compartido.
- [`src/llm/providers.py`](/home/maurol/dev/K-Chat/src/llm/providers.py) resuelve el provider activo.
- [`src/llm/api_call.py`](/home/maurol/dev/K-Chat/src/llm/api_call.py) envuelve la llamada al provider con retry.
- [`src/llm/discovery.py`](/home/maurol/dev/K-Chat/src/llm/discovery.py) descubre modelos.
- [`src/llm/verifier.py`](/home/maurol/dev/K-Chat/src/llm/verifier.py) valida modelos candidatos.
- [`src/llm/selector.py`](/home/maurol/dev/K-Chat/src/llm/selector.py) elige el modelo por defecto.
- [`src/llm/failover.py`](/home/maurol/dev/K-Chat/src/llm/failover.py) coordina el cambio cuando algo falla.
- [`src/llm/client.py`](/home/maurol/dev/K-Chat/src/llm/client.py) sigue siendo el orquestador de entrada para chat normal y streaming.

## 3. Puntaje

- Desacople del bloque LLM: **8.2/10**
- Contratos y límites: **8.4/10**
- Robustez ante regresiones: **8.1/10**
- Legibilidad operativa: **7.9/10**

## 4. Lo que está bien

- El estado compartido está encapsulado en `model_state.py`.
- `api_call.py` separa retry del cliente.
- `discovery`, `selector`, `verifier` y `failover` ya no están mezclados en un solo archivo.
- El cliente no conoce la implementación concreta del provider.
- El fallback de `chat_stream()` ahora actualiza el system prompt cuando cambia de modelo.

## 5. Riesgos que todavía quedan

| Riesgo | Impacto | Estado |
|---|---|---|
| `client.py` sigue concentrando demasiada orquestación | Medio | Correcto, pero es el bloque más denso |
| `providers.py` usa singleton global | Medio | Aceptable hoy, rígido para multi-provider avanzado |
| `model_state.py` es estado global mutable | Medio | Protegido por lock, pero sigue siendo shared state |
| `_switch_model()` prioriza fallback de forma implícita | Medio | Funciona, pero la política no es obvia a primera vista |
| `verify_model()` usa un ping mínimo muy optimista | Bajo/medio | Puede marcar verde un modelo que luego falle bajo carga |

## 6. Qué no romper

1. `chat()` y `chat_stream()` deben seguir respetando el modelo seleccionado/fallback.
2. El system prompt debe reescribirse cuando se cambia de modelo y existe `build_prompt_fn`.
3. `stream_options={"include_usage": True}` debe mantenerse para streaming.
4. Un error de stream no debe dejar el sistema sin posibilidad de failover.
5. El retry rate-limit no debe confundirse con error de modelo.

## 7. Regresión cubierta

- [`tests/unit/test_client.py`](/home/maurol/dev/K-Chat/tests/unit/test_client.py)
- Nuevo caso: si `chat_stream()` cae al fallback, el system prompt se actualiza con el nuevo modelo.

## 8. Lectura del log que compartiste

Los mensajes `{"type":"model","message":"The model encountered an error. Please try again."}` no apuntan a SearXNG.
Ese mensaje sale del clasificador de errores de stream y normalmente indica que el provider/modelo devolvió un fallo genérico.

El warning de SearXNG es otra capa distinta:
- afecta al auto-start del buscador
- solo toca `web_search`
- no explica por sí solo un error de `model`

## 9. Próximo corte razonable

Si se quiere seguir bajando acople en LLM, el siguiente paso útil es:
1. extraer la política de failover/stream fallback a un coordinador dedicado.
2. convertir `model_state.py` en un objeto inyectable en vez de un singleton global.
3. separar el procesamiento de chunks/tool del `client.py`.
