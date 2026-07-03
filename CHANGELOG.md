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
- **`test_anti_regression.py`** — 6 nuevos tests anti-regresión para el venv:
  - `test_fastembed_is_importable` — Verifica que fastembed se puede importar
  - `test_project_venv_has_python_and_venv_bin_python` — venv/bin/python existe y ejecuta
  - `test_project_venv_has_fastembed_wheel` — fastembed instalado en venv
  - `test_dot_venv_symlink_is_valid` — .venv symlink válida hacia venv/
  - `test_active_python_prefix_is_not_system` — Detecta si tests corren con python sistema
  - `test_scripts_test_sh_exists_and_uses_venv` — scripts/test.sh existe y usa venv

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

### Archivos modificados
- `src/memory/repos/session_repository.py`
- `src/memory/repos_memory/work_catalog_repo.py`
- `src/memory/vector/store.py`
- `src/memory/curator/curate.py`
- `tests/unit/test_repositories.py`
- `tests/unit/test_chat_router.py`
- `tests/unit/test_anti_regression.py`
- `scripts/kairos-node.sh`
- `scripts/test.sh` (nuevo)
- `docs/debug_20260703_connection_refused.md` (nuevo)