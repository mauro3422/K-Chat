# Auditoría de `src/core/tool_loop.py`

## 1. Qué cubre

Este bloque coordina:
- el loop de herramientas en streaming
- el loop síncrono de CLI
- persistencia del assistant turn con tool calls
- debug de reasoning y tool_calls
- chunking del contenido final cuando no hay stream incremental

## 2. Corte de responsabilidades actual

- [`src/core/tool_loop.py`](/home/maurol/dev/K-Chat/src/core/tool_loop.py) sigue siendo el coordinador central.
- [`src/constants.py`](/home/maurol/dev/K-Chat/src/constants.py) ahora concentra la política compartida de `MAX_TOOL_TURNS` y `TOOL_OUTPUT_CHUNK_SIZE`.
- [`src.memory.repos.MessageRepository`](/home/maurol/dev/K-Chat/src/memory/repos/message_repository.py) es la ruta de persistencia para assistant tool turns.
- [`src.tools.runner`](/home/maurol/dev/K-Chat/src/tools/runner.py) sigue ejecutando batch de herramientas.

## 3. Puntaje

- Desacople del bloque tool loop: **8.1/10**
- Contratos y límites: **8.4/10**
- Robustez ante regresiones: **8.2/10**
- Legibilidad operativa: **7.8/10**

## 4. Lo que está bien

- `ToolLoopContext` encapsula estado que antes vivía disperso.
- La política de chunking ya no está hardcodeada dentro del loop.
- El `MAX_TOOL_TURNS` compartido quedó fuera del archivo feature.
- La persistencia del assistant turn con tools ya no depende de SQL suelto.
- El loop streaming y el sync comparten estructura base.

## 5. Riesgos que todavía quedan

| Riesgo | Impacto | Estado |
|---|---|---|
| `tool_loop.py` sigue siendo un coordinador denso | Medio | Aceptable, pero todavía concentra lógica |
| `llm_chat_fn` y `llm_chat_stream_fn` siguen tipados como `Callable[..., Any]` | Bajo/medio | Funciona, pero el contrato es blando |
| el fallback de stream vive en el loop y en el cliente LLM | Medio | Funciona, pero es una frontera compartida |

## 6. Qué no romper

1. `run_tool_loop_streaming()` debe seguir emitiendo reasoning/content/tool_call con el mismo contrato.
2. `run_tool_loop_sync()` debe conservar el mismo semántico de turnos.
3. El fallback de contenido sin stream debe seguir chunking estable.
4. La persistencia del assistant turn con tools debe seguir usando repositorios.
5. El debug debe seguir recibiendo reasoning y tool_calls.

## 7. Regresiones cubiertas

- [`tests/unit/test_tool_loop_sync.py`](/home/maurol/dev/K-Chat/tests/unit/test_tool_loop_sync.py)
- [`tests/unit/test_tool_loop_streaming.py`](/home/maurol/dev/K-Chat/tests/unit/test_tool_loop_streaming.py)
- [`tests/unit/test_contracts.py`](/home/maurol/dev/K-Chat/tests/unit/test_contracts.py)

## 8. Próximo corte razonable

Si se quiere seguir limpiando este bloque, el siguiente paso útil es:
1. extraer una política explícita para el fallback de stream.
2. tipar mejor los callbacks `llm_chat_fn` / `llm_chat_stream_fn`.
