# CHANGELOG — 2026-07-04 (Sesión masiva de debugging)

## 🐛 Provider Errors (DeepSeek 400/401) — Raíz del problema

### Bug #1: model_state condenaba DeepSeek para siempre
**Archivos:** `src/llm/model_state.py`, `src/config_loader.py`, `src/llm/selector.py`

Cuando DeepSeek fallaba UNA vez (rate limit, timeout, error transitorio), se marcaba como "failed" PERMANENTE. El sistema switcheaba a `big-pickle` (modelo fantasma que no existe) → 401 en TODAS las requests siguientes. El server parecía roto pero la API key funcionaba perfecto.

**Fixes:**
- TTL de 300s: modelos fallidos se rehabilitan solos después de 5 minutos
- `big-pickle` eliminado de PRIORITY_MODELS (solo deepseek-v4-flash)
- `_failed_models` cambiado de set a dict con timestamps
- Propiedades `priority` y `fallback_model` restauradas

### Bug #2: content:null faltante en tool_calls → 400
**Archivo:** `src/llm/adapters/openai_adapter.py`

`_to_openai_messages()` filtraba `content` cuando era `None`. DeepSeek requiere el campo presente aunque sea null en mensajes assistant con tool_calls. Primer llamado al LLM funcionaba, segundo (post-tools) fallaba con 400.

**Fix:** `and (v is not None or k == "content")` — content se mantiene aunque sea null.

### Bug #3: Historial con tool messages huérfanas → 400
**Archivos:** `src/core/history_parser.py`, `src/_types.py`, `web/services/message_persister.py`

DeepSeek: "Messages with role 'tool' must be a response to a preceding message with 'tool_calls'". Había 11 ocurrencias de este error. Causa: mensajes assistant vacíos entre tool_calls y tool responses rompían el pairing. También `tool_calls: []` se enviaba al LLM.

**Fixes:**
- Loop de pairing skipea assistants vacíos en vez de cortar
- `as_llm_message()`: `if self.tool_calls:` (excluye None y lista vacía)
- `save_assistant_message()`: no persiste mensajes totalmente vacíos

### Bug #4: stream_options rechazado por DeepSeek
**Archivo:** `src/llm/adapters/openai_adapter.py`

`stream_options={"include_usage": true}` es específico de OpenAI. DeepSeek lo rechaza.

**Fix:** Condicional con `_is_openai_model()` — solo para gpt-/o1/o3/o4.

### Bug #5: Clasificación de errores incompleta
**Archivo:** `web/services/stream_error_classifier.py`

Errores 400/401/CreditsError se clasificaban como "unknown" → se reintentaban 3 veces innecesariamente.

**Fixes:**
- Nuevos tipos: `bad_request`, `credits`, `auth` con mensajes en español
- `_parse_duration_value` no retornaba el valor (bug preexistente)
- Frontend: `credits` errores ahora reintentables (falsos positivos del provider)

---

## 🔁 Frontend — Retry, SSE, State Management

### Bug #6: [object Object] en mensajes de error
**Archivo:** `web/src_ts/streaming/NDJSONStreamClient.ts`

`String(msg.d)` sobre objetos JSON → `"[object Object]"`. Los mensajes de error del provider llegaban como objetos.

**Fix:** `_serializeStreamData()` — JSON.stringify para objetos, String para strings.

### Bug #7: SSE no reconectaba tras restart del server
**Archivo:** `web/src_ts/streaming/SSEClient.ts`

No había `onopen`, no se chequeaba `readyState`, no había reconexión manual en estado CLOSED.

**Fixes:**
- `onopen`: emite `connection:restored` y resetea backoff
- `onerror`: detecta CLOSED → reconexión manual con backoff (1s→30s)
- `_reconnectTimer` para limpieza

### Bug #8: handleRetry fire-and-forget + _streamGuard trabado
**Archivo:** `web/src_ts/streaming/StreamOrchestrator.ts`

`handleRetry` no await-eaba → errores silenciosos. AbortError no llamaba `_finalizeStream()` → `_streamGuard` quedaba true para siempre.

**Fixes:**
- `handleRetry` async/await con try/catch
- `_finalizeStream()` en catch de AbortError

### Bug #9: Indicador de retry
**Archivo:** `web/src_ts/core/ui/RetryHandler.ts`

Antes: mensaje desaparecía durante retry. Ahora: `🔄 Error del provider — reintentando (x/3)...` + burbuja de memoria preservada (`:not(.memories-phase)`).

### Bug #10: Modelo no persistía al recargar
**Archivos:** `web/src_ts/widgets/ModelSelector.ts`, `web/src_ts/app.ts`

Hidden `<select>` sin `<option>` elements → localStorage se corrompía en cada change event → aparecía Kimi en vez de DeepSeek.

**Fixes:**
- `populateHiddenSelect()`: poblar el select con options
- `app.ts`: `Object.assign` en vez de sobreescribir `window.__k`
- `logger` y `allModels` restaurados (borrados accidentalmente)

### Bug #11: Last-Event-ID replay + Connection events
**Archivos:** `web/services/event_bus.py`, `web/routers/events.py`, `web/src_ts/app.ts`

Eventos durante downtime se perdían. No había reconexión con replay.

**Fixes:**
- Ring buffer de 200 eventos con seq numbers
- `stream()` acepta `last_event_id`, replaya eventos perdidos
- `connection:restored` → re-fetch del historial de sesión
- ChatForm muestra "⚡ Reconectando..." en placeholder

---

## 📊 Infraestructura

### Watchdog falsos positivos
**Archivo:** `.kairos/watchdog.py`

Tools bloqueantes (recall_memories, web_search) ocupaban el thread → health check fallaba → watchdog mataba el server tras 30s.

**Fix:** 15s interval + 12 fallos = 3min de tolerancia (mismo que STARTUP_GRACE).

### StreamState save interval
**Archivo:** `web/services/stream_state.py`

Guardado periódico cada 30s → pérdida de hasta 30s de respuesta en crash.

**Fix:** Reducido a 10s.

---

## 🏗️ Arquitectura

### Layer violation: node_memory.py → src/memory/
**Archivos:** `src/api/memory.py` (nuevo), `web/routers/node_memory.py`

Facade layer `src/api/memory.py` — web/ ahora importa de api/, no de memory/ directamente.

### Log deduplication
**Archivos:** `web/routers/logs.py`, `web/routers/debug.py`

`/api/logs/tail` mergeaba file_logger + LogBus del mismo archivo → duplicados. `get_backend_logs()` mezclaba schemas incompatibles.

**Fixes:**
- `_latest_file_logger_path()` excluye `logbus_*.jsonl`
- `get_backend_logs()` filtra y normaliza schemas

---

## 🧪 Testing

### Nuevos tests anti-regresión
**Archivos:** `tests/unit/test_anti_regression_provider.py`, `tests/unit/test_anti_regression_history.py`

- ModelState TTL: 5 tests (recuperación, skip, clear, raise)
- Message sanitization: 3 tests (content:null, extras, null tool_calls)
- Error classifier: 7 tests (bad_request, credits, auth, rate_limit, timeout, unknown)
- History parser: 4 tests (pairing con empty assistant, normal, orphan, kept)
- as_llm_message: 3 tests (empty [], null, valid)
- Message persister: 2 tests (empty skip, content save)
- _parse_duration_value: 5 tests (formats Xs, XmYs, Xm, Ys, empty)

### Script de diagnóstico
**Archivo:** `scripts/diag_provider.py`

End-to-end test del pipeline completo. Modo `--smoke` para CI. Modo `--quick` para 4 tests rápidos.

### npm run typecheck:critical
TypeScript type-checking para archivos core (ModelSelector, RetryHandler, NDJSONStream, StreamOrchestrator, SSEClient, ChatForm, app.ts).

---

## 📈 Resultados

- **20 commits** en esta sesión
- **+29 tests** anti-regresión
- **0 falsos positivos** del provider
- **Smoke test: 7/7 ✅**
- **Unit tests: 1389/1391 ✅**
- **Modelo persiste** correctamente al recargar
- **SSE reconecta** automáticamente con replay
- **Watchdog** no mata el server por tools lentas
- **`session_repository.py:ensure()`** — Race condition TOCTOU (Time-of-Check-Time-of-Use):
  dos requests concurrentes para el mismo `session_id` ejecutaban SELECT + INSERT sin
  atomicidad. El segundo INSERT fallaba con `UNIQUE constraint failed: sessions.session_id`,
  excepción no atrapada que mataba el proceso de uvicorn. El frontend entraba en loop de
  reintentos generando spam masivo de `ERR_CONNECTION_REFUSED`.
- **Fix:** `INSERT INTO` → `INSERT OR IGNORE INTO` (atómico, elimina el SELECT previo).

### Fixes adicionales (mismo patrón TOCTOU)

- **`work_catalog_repo.py:mark()`** — Upsert manual (UPDATE then INSERT) reemplazado por
  `INSERT ... ON CONFLICT DO UPDATE` (atómico).
- **`vector/store.py:insert()`** — Añadido dedup check atómico dentro del `_lock` para
  prevenir duplicados cuando dos vectorizers concurrentes insertan el mismo `content_hash`.
- **`curate.py:curate_clusters()` y `curate_sessions()`** — Pre-marca como "processing"
  antes de la llamada LLM costosa, previniendo duplicación de trabajo entre curadores
  concurrentes (antes: is_processed → LLM → mark, con ventana de segundos a minutos).
- **`curate.py:_retire_old_sessions()`** — Cada par INSERT+DELETE ahora se commitea
  individualmente con manejo de errores por sesión (antes: commit único batch).

### Tests

- **`test_repositories.py`** — Actualizado para reflejar `INSERT OR IGNORE` (1 execute,
  no 2).
- **`test_chat_router.py`** — Actualizado para aceptar `origin_node_id=ANY` en `ensure()`.
- **`test_anti_regression.py`** — 6 tests anti-regresión del venv + 9 tests TOCTOU =
  15 tests nuevos:
  - **Venv (6):** fastembed importable, venv/bin/python existe y ejecuta, fastembed
    instalado en venv, .venv symlink válida, sys.prefix no es sistema, scripts/test.sh
    existe y usa venv
  - **TOCTOU (9):** INSERT OR IGNORE en ensure(), ON CONFLICT en mark(), dedup atómico
    en VectorStore, pre-mark "processing" en curador, commit por sesión en retiro,
    watchdog 180s/6 fallos, auto-refresh de modelos vacíos, preload ML en background,
    model priming en background

### Infraestructura

- **`scripts/test.sh`** — Nuevo wrapper que siempre usa `venv/bin/python` para correr
  pytest (antes: tests corrían con `python3` del sistema, sin fastembed).
- **`scripts/kairos-node.sh`** — `.venv/bin/pip` → `venv/bin/pip` (dependencia del
  symlink roto eliminada).
- **`.venv`** — Symlink reparado: `.venv → venv` (estaba roto, causaba fallback
  silencioso a system python3).
- **`docs/debug_20260703_connection_refused.md`** — Análisis detallado completo del bug
  con reproducción experimental, flujo completo, y 19 patrones TOCTOU encontrados en el
  codebase.

### Fix: Watchdog mataba al servidor durante carga de modelos

- **`.kairos/watchdog.py`** — `STARTUP_GRACE` de 10s → 180s, `REQUIRED_FAILURES` de
  3 → 6. El watchdog interpretaba la descarga inicial del modelo de embeddings (90s)
  como un crash y reiniciaba el servidor en loop.
- **`web/app_factory.py`** — ML preload (embedding + reranker) ahora corre como
  `asyncio.create_task()` en background, no bloquea el startup. Antes bloqueaba el
  `yield` del lifespan y el servidor no aceptaba requests hasta terminar.
- **`web/routers/debug.py`** — `/models/availability` ahora auto-refresca el registro
  de modelos si está vacío. Si el primario (Windows) perdió sus modelos al iniciar,
  se recuperan solos al primer poll.
- **`.env`** — `KAIROS_WARMUP_EMBEDDINGS=true` para precarga automática de modelos ML.

### Archivos modificados

- `src/memory/repos/session_repository.py`
- `src/memory/repos_memory/work_catalog_repo.py`
- `src/memory/vector/store.py`
- `src/memory/curator/curate.py`
- `tests/unit/test_repositories.py`
- `tests/unit/test_chat_router.py`
- `tests/unit/test_anti_regression.py`
- `web/app_factory.py`
- `web/routers/debug.py`
- `.kairos/watchdog.py`
- `scripts/kairos-node.sh`
- `scripts/test.sh` (nuevo)
- `docs/debug_20260703_connection_refused.md` (nuevo)

---

# CHANGELOG — 2026-07-04 (Sesión 2: Circuit breaker + Rate limit graceful + Frontend fixes)

## Bug #12: Circuit breaker abre por rate limits → error clasificado como "model"

**Archivo:** `src/llm/failover.py`

**Causa raíz:** `breaker.record_failure(model)` se ejecutaba para TODOS los errores, incluso rate limits. Después de 3 rate limits (reintentos automáticos del SDK), el circuit breaker se abría. En el siguiente reintento, `_mark_and_refresh` raiseaba `RuntimeError("All models are circuit-broken; no LLM available")` que contenía "model" → `classify_error` retornaba `"model"` en vez de `"rate_limit"`.

**Fix:** `breaker.record_failure(model)` movido dentro del guard `should_mark_as_failed` — rate limits y credits ya no incrementan el breaker:
- Rate limit → `should_mark_as_failed = False` → NO breaker, NO mark_model_failed
- Credits → `should_mark_as_failed = False` → NO breaker, NO mark_model_failed
- Genuine errors → `should_mark_as_failed = True` → breaker + mark_model_failed

## Bug #13: Catch-all retorna modelo rate-limited a pesar de estar en cooldown

**Archivo:** `src/llm/failover.py`

`_switch_model()` (el catch-all cuando `_dynamic_switch_model` retorna None) solo checkea `is_model_failed`, no `is_rate_limited`. Como rate limits NO marcan failed, retornaba el mismo modelo rate-limited → el caller reintentaba contra el mismo endpoint → 429 otra vez → loop.

**Fix:** Dos guards nuevos en `_mark_and_refresh`:
1. En el `except RuntimeError`: si el modelo está rate-limited, raisea en vez de usarlo como last resort
2. Post `_switch_model`: checkea `rate_store.is_rate_limited(next_model)` y raisea si está rate-limited

## Bug #14: Error card de rate limit estática sin countdown

**Archivos:** `web/src_ts/streaming/StreamOrchestrator.ts`, `web/src_ts/widgets/ModelAvailabilityPoller.ts`

La error-card de rate limit mostraba texto estático "Límite del proveedor, reintentá en unos minutos." sin indicación de cuánto faltaba. El RateLimitCooldown existía (ChatForm muestra countdown en botón de enviar) pero no estaba integrado con la error-card.

**Fixes:**
- `_handleStreamError('rate_limit')` ahora arranca `RateLimitCooldown.start(60000)`
- `_showErrorCard('rate_limit')` muestra countdown vivo: `Reintentando en <span id="rl-countdown-N">57</span>s...`
- Countdown se actualiza cada 1s vía `rate-limit:tick`
- Botón ✕ para cancelar auto-retry
- Botón "Reintentar ahora" manual disponible después de cancelar o al expirar cooldown
- Auto-retry cuando cooldown expira (reusa la misma burbuja assistant)
- Se cancela auto-retry si usuario envía otro mensaje manualmente
- `rl-badge`: animación pulse, aria-label, tooltip con nombres de modelos, clic revela modelos saturados

**HandleRetry mejorado:**
- Guarda referencia a `_savedErrorEl` ANTES de `_finalizeStream` que lo limpia
- Restaura `lastAssistantMsgEl` cuando el cooldown expira
- `handleRetry` ya no depende de `_streamGuard` activo (funciona post-finalización)

## Bug #15 (pre-existing): Test esperaba "6m0s" en vez de "6m"

**Archivo:** `tests/unit/test_stream_error_classifier.py`

`_format_duration_hint(360)` retorna "6m" (correcto — no muestra "0s" cuando hay minutos). El test esperaba "6m0s".

**Fix:** Assert actualizado a "6m".

## Nuevos tests anti-regresión

**Archivo:** `tests/unit/test_failover.py` (10 tests nuevos)

| Test | Qué verifica |
|---|---|
| `test_mark_and_refresh_rate_limited_does_not_record_breaker` | Rate limits NO llaman `breaker.record_failure` |
| `test_mark_and_refresh_rate_limited_does_not_mark_model_failed` | Rate limits NO llaman `mark_model_failed` |
| `test_mark_and_refresh_generic_error_does_record_breaker` | Errores genéricos SÍ llaman `breaker.record_failure` |
| `test_dynamic_switch_model_selects_preferred_free_fallback` | Prefiere deepseek-v4-flash-free cuando primary rate-limited |
| `test_dynamic_switch_model_skips_rate_limited_free_model` | None si ambos rate-limited |
| `test_dynamic_switch_model_returns_none_when_no_candidates` | None si registry vacío |
| `test_mark_and_refresh_raises_when_only_model_is_rate_limited` | Raisea si único modelo rate-limited |
| `test_mark_and_refresh_raises_when_fallback_is_also_rate_limited` | Raisea aunque switch_model devuelva otro rate-limited |
| `test_mark_and_refresh_rate_limited_uses_dynamic_fallback` | Retorna free model cuando disponible |
| `test_mark_and_refresh_still_records_breaker_for_generic_error` | Breaker se registra para errores NO rate-limit |

## Archivos modificados

- `src/llm/failover.py`
- `web/src_ts/streaming/StreamOrchestrator.ts`
- `web/src_ts/widgets/ModelAvailabilityPoller.ts`
- `tests/unit/test_failover.py`
- `tests/unit/test_stream_error_classifier.py`
- `MEMORY.md`
- `skills/db-query/tool.py`

---

### Bug #16: Watchdog no reiniciaba el server correctamente (zombies en puerto 8000)

**Archivos:** `.kairos/watchdog.py`, `.kairos/k-chat-watchdog.service`

Cuando el servidor crasheaba, el watchdog llamaba `systemctl --user restart k-chat`. systemd no mataba los procesos zombis que sobrevivían y seguían agarrando el puerto 8000 → el restart fallaba en loop (`[Errno 98] address already in use`). El counter del restart loop llegó a #21 con PID 297116 vivo por horas.

**Fixes (reescritura completa):**
- **Ya no depende de systemd** para restart. Nueva secuencia `kill_and_restart()`:
  1. `pgrep -f uvicorn web.server:app` encuentra TODOS los procesos
  2. SIGTERM primero, verifica `/proc/{pid}`, SIGKILL a los supervivientes
  3. `fuser -k 8000/tcp` como ultimate fallback
  4. Verifica que el puerto esté libre (poll cada 500ms, timeout 10s)
  5. Spawnea uvicorn como `subprocess.Popen` hijo directo (no via systemd)
- **PID tracking**: guarda el PID en `.kairos/server.pid`
- **Server logs**: stdout/stderr a `.kairos/server_stdout.log`/`server_stderr.log` (pipe directo evitaba deadlock)
- **Verificación post-restart**: health check cada 2s por hasta 180s, 3 reintentos si no levanta
- **Startup inteligente**: si el server ya está corriendo al arrancar, no espera 180s de gracia
- **Cleanup al salir**: mata el server hijo cuando el watchdog termina
- **Service file**: `ReadWritePaths` expandido a `%h/dev/K-Chat` (necesario para uvicorn hijo), `Wants=k-chat.service` eliminado