# CHANGELOG — 2026-07-03

## Fix: Race condition TOCTOU que crasheaba el servidor (ERR_CONNECTION_REFUSED)

### Bug principal
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