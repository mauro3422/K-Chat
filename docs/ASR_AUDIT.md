# ASR Audit

Este documento audita el bloque de audio y transcripción como una unidad lego dentro de K-Chat.

## Resumen ejecutivo

El bloque ASR ya está bastante bien desacoplado:

- captura de audio en frontend separada del transporte
- segmentación VAD separada del merge textual
- contrato compartido para telemetría, texto visible y config
- router FastAPI con WebSocket real y endpoint HTTP servidor
- persistencia de telemetría aislada en `src.api.debug` / `DebugRepository`

Lo que todavía no conviene tocar a ciegas:

- la heurística de merge/puntuación
- la segmentación VAD
- el contrato de eventos ASR
- el handshake del WebSocket

## Puntaje general

- **Desacople del bloque ASR:** 8.8/10
- **Contratos y límites:** 8.6/10
- **Robustez frente a regresiones:** 8.4/10
- **Legibilidad operativa:** 8.7/10
- **Riesgo de rotura por cambios locales:** bajo-medio

## Matriz de riesgo

Si algo rompe el ASR, este es el orden en que conviene mirar:

1. `web/static/modules/asr/contract.js`
2. `web/static/modules/asr/transcript-utils.js`
3. `web/static/modules/asr/vad.js`
4. `web/static/modules/asr/transcription-transport.js`
5. `web/routers/asr.py`
6. `web/services/asr_service.py`
7. `web/static/modules/debug-panel.js`

Por qué:
- si se rompe el contrato, se rompe la UI y el panel de debug al mismo tiempo
- si se rompe el merge, el texto se duplica o pierde palabras
- si se rompe el VAD, cambian los cortes y la latencia
- si se rompe el transporte, la transcripción deja de entrar aunque el resto siga sano
- si se rompe el router o el servicio, el problema pasa a ser backend

## Mapa de capas

### 1. Captura de audio

Archivos:
- [`web/static/modules/asr/audio-capture.js`](/home/maurol/dev/K-Chat/web/static/modules/asr/audio-capture.js)
- [`web/static/modules/asr/pcm-worklet.js`](/home/maurol/dev/K-Chat/web/static/modules/asr/pcm-worklet.js)

Puntaje: **9.2/10**

Observaciones:
- `AudioWorklet` ya reemplazó al camino viejo.
- La captura está bien aislada del resto del flujo.
- El módulo no sabe nada de backend, sesiones ni UI.

Riesgos:
- cambios en sample rate o frame size pueden alterar la segmentación.

### 2. Segmentación VAD

Archivo:
- [`web/static/modules/asr/vad.js`](/home/maurol/dev/K-Chat/web/static/modules/asr/vad.js)

Puntaje: **8.7/10**

Observaciones:
- el segmentador tiene parámetros claros
- el pre-roll y el overlap ayudan a no cortar palabras
- el flush final está aislado

Riesgos:
- si se aprieta demasiado `endSilenceMs` o `maxSegmentMs`, vuelve la pérdida de contexto
- si se sube demasiado `overlapMs`, reaparecen duplicados

### 3. Transporte ASR

Archivo:
- [`web/static/modules/asr/transcription-transport.js`](/home/maurol/dev/K-Chat/web/static/modules/asr/transcription-transport.js)

Puntaje: **8.8/10**

Observaciones:
- el cliente usa `WebSocket` como canal único
- el transport no mezcla la lógica de UI
- el handshake con `session_id` está explícito
- la respuesta se resuelve por mensaje `transcript`

Riesgos:
- si el backend deja de montar `/api/asr/stream`, el cliente falla en forma visible
- cualquier cambio en el formato del mensaje WS rompe el roundtrip

### 4. Router y servicio backend

Archivos:
- [`web/routers/asr.py`](/home/maurol/dev/K-Chat/web/routers/asr.py)
- [`web/services/asr_service.py`](/home/maurol/dev/K-Chat/web/services/asr_service.py)

Puntaje: **8.5/10**

Observaciones:
- el router recibe audio por HTTP y por WebSocket
- la transcripción real vive en el servicio
- la telemetría se persiste en la capa de debug
- el router sigue siendo fino, pero concentra dos transportes

Riesgos:
- si se toca el formato de payload, hay que actualizar router y tests
- el servicio depende de ffmpeg y `speech_recognition`

### 5. Contrato compartido

Archivo:
- [`web/static/modules/asr/contract.js`](/home/maurol/dev/K-Chat/web/static/modules/asr/contract.js)

Puntaje: **8.9/10**

Observaciones:
- centraliza el estado visible del ASR
- centraliza telemetría y config
- evita que `debug-panel` y `asr-mic` se peguen a globals arbitrarios

Riesgos:
- si aparece otro consumidor, conviene que use este contrato y no globals directos

### 6. Merge y puntuación

Archivo:
- [`web/static/modules/asr/transcript-utils.js`](/home/maurol/dev/K-Chat/web/static/modules/asr/transcript-utils.js)

Puntaje: **8.2/10**

Observaciones:
- la lógica ya no está escondida dentro del orquestador
- el overlap de segmentos está controlado
- la puntuación es heurística y conservadora

Riesgos:
- cambios agresivos pueden mejorar una frase pero empeorar diez
- esta parte es la más sensible a regresiones semánticas

### 7. Debug y observabilidad

Archivo:
- [`web/static/modules/debug-panel.js`](/home/maurol/dev/K-Chat/web/static/modules/debug-panel.js)

Puntaje: **8.3/10**

Observaciones:
- el panel muestra transporte, texto vivo y telemetría
- ya no depende directamente de una sola ruta backend
- `asr:telemetry` y `asr:text` están normalizados

Riesgos:
- si el contrato cambia, el debug debe actualizarse en espejo

## Puntaje de acoplamiento por riesgo

Más alto significa más riesgo de rotura al tocarlo.

1. `transcript-utils.js` - 8.7/10
1. `vad.js` - 8.4/10
1. `web/routers/asr.py` - 8.2/10
1. `transcription-transport.js` - 8.1/10
1. `asr/contract.js` - 7.8/10
1. `debug-panel.js` - 7.6/10

Interpretación:
- el bloque está bien modularizado
- el riesgo ya no está en “todo junto”, sino en los bordes de contrato

## Anti-regresiones que ya deberían existir

- el router debe registrar `/api/asr/transcribe`
- el router debe registrar `/api/asr/stream`
- el WebSocket debe aceptar bytes y devolver `{"type":"transcript"}`
- la telemetría debe persistir por sesión
- el contrato JS debe exponer texto visible y telemetría
- el merge debe conservar solapamientos sin duplicarlos de más
- la puntuación debe seguir apareciendo en el texto visible

## Cobertura real actual

Ya hay pruebas que cubren:

- contrato JS de ASR
- merge y puntuación de transcript
- VAD y encoding PCM/WAV
- router ASR y su registro de rutas
- append/persistencia de telemetría ASR en backend
- servicio de transcripción y helpers de ffmpeg

Esa cobertura no hace inmune al bloque, pero sí corta los fallos típicos:

- cambios de forma del mensaje WS
- regresión de `asr:telemetry`
- pérdida del texto visible
- duplicación de solapamientos
- rotura del handshake o de la ruta registrada

## Lo que todavía no conviene romper

- `session_id` en el WS query string
- payload binario WAV por segmento
- `transport: "ws"` en telemetría
- `asr:telemetry` y `asr:text`
- la separación entre contrato, transporte y orquestación

## Qué tocar primero si querés seguir endureciendo

1. `transcript-utils.js`
2. `vad.js`
3. `asr/contract.js`
4. `debug-panel.js`
5. `web/routers/asr.py`

Ese orden minimiza el riesgo:
- primero la lógica pura
- después los bordes de estado
- al final backend e integración visual

## Veredicto

Sí, el bloque ASR ya es un lego razonable dentro del sistema.
No está perfecto, pero ya no es un “monolito escondido”.
La mayor defensa contra regresiones ahora no es seguir juntando código, sino mantener:

- contratos pequeños
- tests de transporte y merge
- una sola fuente de verdad para telemetría/texto
- cambios graduales en VAD y puntuación
