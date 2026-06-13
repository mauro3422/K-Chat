# Stream Audit

Auditoría del bloque de chat streaming NDJSON, retry y persistencia parcial.

## Resumen ejecutivo

Este bloque está bastante bien modularizado, pero sigue siendo uno de los más sensibles del sistema porque junta:

- entrada HTTP de chat
- reconstrucción de historial
- generación NDJSON
- detección de loops
- recuperación por retry
- persistencia parcial/final
- auto-rename asíncrono
- contrato frontend/backend de eventos

La buena noticia:

- ya hay contrato compartido de stream
- el fetcher frontend y el router backend hablan el mismo NDJSON
- la persistencia parcial existe y está probada
- la recuperación por interrupción tiene tests

La mala noticia:

- el orquestador sigue siendo un punto con demasiada responsabilidad
- cualquier cambio pequeño en contrato o retry puede romper varias capas a la vez

## Puntaje general

- **Desacople del bloque streaming:** 8.1/10
- **Contratos y límites:** 8.5/10
- **Robustez ante regresiones:** 8.3/10
- **Legibilidad operativa:** 7.9/10
- **Riesgo de rotura por cambios locales:** medio

## Mapa de capas

### 1. Router de chat

Archivo:
- [`web/routers/chat.py`](/home/maurol/dev/K-Chat/web/routers/chat.py)

Puntaje: **8.0/10**

Observaciones:
- el router valida entrada y arma la respuesta stream
- mantiene las dependencias de sesión, historial y generator inyectadas
- expone un punto único de entrada HTTP

Riesgos:
- si cambia la forma de `ChatPayload`, rompe compatibilidad externa
- si cambia la firma de `build_stream_generator`, el router se vuelve el primer punto en fallar

### 2. Generador de stream

Archivo:
- [`web/services/chat_stream.py`](/home/maurol/dev/K-Chat/web/services/chat_stream.py)

Puntaje: **7.6/10**

Observaciones:
- aquí vive la parte más delicada
- maneja tokenización NDJSON, saves parciales, retries, loop detection y renaming
- la lógica está clara, pero sigue muy cargada

Riesgos:
- acumulación de responsabilidades
- regresiones al tocar `full_content`, `full_reasoning` o `phases_output`
- pérdida de comportamiento si se cambia el orden de save/retry/finalize

### 3. Contrato de stream

Archivos:
- [`web/services/stream_contract.py`](/home/maurol/dev/K-Chat/web/services/stream_contract.py)
- [`web/static/modules/stream-contract.js`](/home/maurol/dev/K-Chat/web/static/modules/stream-contract.js)

Puntaje: **8.8/10**

Observaciones:
- el contrato ya es explícito
- server y frontend usan `t` y `d`
- validación y serialización son simples

Riesgos:
- añadir nuevos tipos sin actualizar ambos lados

### 4. Fetcher frontend

Archivo:
- [`web/static/modules/stream-fetcher.js`](/home/maurol/dev/K-Chat/web/static/modules/stream-fetcher.js)

Puntaje: **8.2/10**

Observaciones:
- consume NDJSON línea por línea
- maneja abort y errores de HTTP bien
- diferencia heartbeat/content/reasoning/tool_call/error

Riesgos:
- si el backend devuelve JSON inválido o corta líneas, aparecen parse errors
- si cambian tipos de evento, el frontend debe actualizarse junto con el contrato

### 5. Retry y recuperación

Archivos:
- [`web/services/stream_retry_handler.py`](/home/maurol/dev/K-Chat/web/services/stream_retry_handler.py)
- [`web/services/stream_error_classifier.py`](/home/maurol/dev/K-Chat/web/services/stream_error_classifier.py)

Puntaje: **8.4/10**

Observaciones:
- la recuperación está encapsulada
- el continuation prompt es claro
- la clasificación de errores tiene reglas visibles y tests

Riesgos:
- un cambio en la clasificación puede modificar cuándo reintenta el chat
- `attempt_recovery()` depende de que el modelo acepte la continuidad sin degradarse

### 6. Persistencia de salida parcial

Archivo:
- [`web/services/message_persister.py`](/home/maurol/dev/K-Chat/web/services/message_persister.py)

Puntaje: **8.3/10**

Observaciones:
- persiste assistant content, reasoning y phases
- deduplica fases repetidas
- mantiene debug info junto al mensaje

Riesgos:
- si cambia la estructura de phases o debug, hay que tocar frontend y tests en espejo

### 7. Observabilidad

Archivos:
- [`web/static/modules/debug-panel.js`](/home/maurol/dev/K-Chat/web/static/modules/debug-panel.js)
- [`tests/unit/test_api_debug.py`](/home/maurol/dev/K-Chat/tests/unit/test_api_debug.py)

Puntaje: **7.8/10**

Observaciones:
- hay debug backend y UI
- la telemetría del stream existe
- pero el bloque aún mezcla logs de UI, stream y estado general

Riesgos:
- el panel puede volverse demasiado cargado si se le agregan más formatos sin contrato

## Matriz de riesgo

Si rompe el streaming, revisar en este orden:

1. [`web/services/stream_contract.py`](/home/maurol/dev/K-Chat/web/services/stream_contract.py)
2. [`web/static/modules/stream-contract.js`](/home/maurol/dev/K-Chat/web/static/modules/stream-contract.js)
3. [`web/services/chat_stream.py`](/home/maurol/dev/K-Chat/web/services/chat_stream.py)
4. [`web/static/modules/stream-fetcher.js`](/home/maurol/dev/K-Chat/web/static/modules/stream-fetcher.js)
5. [`web/services/stream_retry_handler.py`](/home/maurol/dev/K-Chat/web/services/stream_retry_handler.py)
6. [`web/services/message_persister.py`](/home/maurol/dev/K-Chat/web/services/message_persister.py)
7. [`web/routers/chat.py`](/home/maurol/dev/K-Chat/web/routers/chat.py)

## Cobertura actual

Ya hay pruebas que cubren:

- contrato NDJSON en Python y JS
- serialización y parseo de eventos
- recuperación/retry
- aborto de stream y persistencia parcial
- router de chat
- error classifier

Lo que eso protege:

- no romper el esquema `t`/`d`
- no perder contenido parcial
- no perder reintentos transparentes
- no degradar a HTTP no esperado sin que se note

## Qué no conviene romper

- `build_stream_generator()` como punto central del NDJSON
- el contrato `{"t": ..., "d": ...}`
- el save parcial en interrupción
- `StreamRetryHandler.build_messages()`
- la clasificación de errores `auth`, `rate_limit`, `network`, `model`

## Veredicto

El bloque streaming ya está suficientemente lego para convivir con el resto del sistema.
Pero sigue siendo el bloque con más lógica pegada en un solo punto.

Si se quiere bajar más el riesgo de rotura, el siguiente paso natural no es meter más features.
Es extraer:

- acumulación de chunks
- política de retry
- persistencia
- y render/event mapping

en piezas todavía más chicas.

