# Laptop stash audit - 2026-07-04

Objetivo: preservar y auditar los cambios viejos que quedaron como stash en la laptop, sin mezclarlos a ciegas en `master`.

Estado base verificado:

- PC `master`, PC `origin/master`, laptop `master`, laptop `origin/master` y GitHub estaban en `b244705512e9c6459ab0ff774d82e783315b7137`.
- Los fixes grandes de UI/reconexion/rate limits del 2026-07-03 y 2026-07-04 estan en `master`.
- Los stashes auditados no son de esos fixes recientes:
  - `stash@{2026-07-02 00:09:48 -0300}` -> `origin/codex/preserve-laptop-autostash-20260702`
  - `stash@{2026-06-12 22:43:21 -0300}` -> `origin/codex/preserve-laptop-wip-20260612`

## Archivos preservados

- `autostash-20260702.patch`: patch exacto del autostash del 2026-07-02.
- `wip-20260612.patch`: patch exacto del WIP del 2026-06-12.

Estos patches reemplazan la necesidad de conservar ramas temporales solo para no perder informacion.

## Resultado por stash

### autostash-20260702

Base: `f7b6030 fix(memory): detect orphan catalog links`

Patch real:

- `.kairos/curator.py`
- `MEMORY.md`

Tamanio:

- 2 files changed
- 61 insertions
- 54 deletions

Resultado de auditoria:

- `.kairos/curator.py` ya esta absorbido en `master` en contenido funcional. La diferencia restante es principalmente formato/saltos de linea.
- `MEMORY.md` contiene checkpoints/synthesis antiguos y reordenamientos de entradas historicas. No conviene aplicar esa version vieja sobre el `MEMORY.md` actual.
- Merge directo contra `master` da conflicto en `.kairos/curator.py` y `MEMORY.md`.

Decision:

- No mergear en `master`.
- Patch archivado por trazabilidad.

### wip-20260612

Base: `9db3a3e clarify changelog history`

Patch real:

- 55 files changed
- 915 insertions
- 770 deletions

Clasificacion contra `master` actual:

- 36 archivos todavia existen.
- 19 archivos ya no existen en `master`.

Archivos que ya no existen y que el WIP intenta modificar:

- `src/api/history.py`
- `src/core/chat_sync.py`
- `src/llm/models.py`
- `src/llm/policy.py`
- `tests/test-chat-stream.test.js`
- `tests/test-dom-ordering.test.js`
- `tests/test-retry-handler.test.js`
- `tests/unit/test_chat_sync.py`
- `web/static/chat-stream.js`
- `web/static/debug.js`
- `web/static/modules/chat-form-bootstrap.js`
- `web/static/modules/chat-form.js`
- `web/static/modules/content-handler.js`
- `web/static/modules/logger.js`
- `web/static/modules/retry-handler.js`
- `web/static/modules/stream-bootstrap.js`
- `web/static/modules/stream-orchestrator.js`
- `web/static/modules/widget-container-renderer.js`
- `web/static/session.js`

Resultado de auditoria:

- Merge directo contra `master` produce conflictos masivos: conflictos de contenido y muchos `modify/delete`.
- El WIP es anterior a migraciones grandes de frontend/TS, arquitectura, stream/retry y memoria.
- La mayoria de las areas tocadas por este WIP fueron reemplazadas o corregidas por commits posteriores.

Decision:

- No mergear en `master`.
- Patch archivado por trazabilidad.
- Si algun comportamiento puntual de este WIP interesa, rescatarlo manualmente desde `wip-20260612.patch` en una rama nueva y con tests focalizados.

## Decision global

No queda trabajo reciente de laptop fuera de `master` relacionado con UI, reconexion, rate limits o fixes de bugs del 2026-07-03/2026-07-04. Esos cambios ya estan integrados.

Los stashes viejos quedan preservados como patches versionados. Las ramas temporales `codex/preserve-laptop-*` pueden borrarse despues de que este archivo este en `master` y sincronizado en PC/laptop/GitHub.

## Untracked laptop audit - 2026-07-18

Base verificada:

- PC `master`, `origin/master`, laptop `master` y laptop `origin/master` estan en `8a430de fix: use liveness endpoint in remote doctor`.
- La laptop tenia archivos no trackeados fuera de `master`; se clasificaron antes de archivarlos.

Clasificacion:

- Rescatado en `master`: el prototipo `scripts/compare_runs.py` inspiro `scripts/compare_candidate_runs.py`, una version local saneada, ASCII, estructurada y con tests.
- No integrar a ciegas: `pmi_script_replacement.py`, `fix_pmi.py`, `test_pmi.py` y `tests/unit/test_pmi_relations.py`. El PMI local actual ya contiene una ruta mas madura con stemming, IDF y compatibilidad de API; estos archivos remotos son prototipos anteriores o parches ad hoc.
- No integrar a ciegas: `src/memory/synthesis/curator.py`, `tests/unit/test_curator.py` y `tests/unit/test_graph_analysis_new.py`. El repo actual ya tiene `src/memory/curator/*`, `src/memory/synthesis/*` y cobertura extensa; el curador remoto duplica caminos y necesita diseno antes de entrar.
- Generado/cache visual: `.playwright-mcp/` contiene capturas y YAMLs de Playwright MCP de julio 2026.
- Vendor suelto: `web/static/d3.min.js` pesa 276 KB y no esta referenciado por `master` en esta auditoria.
- Peligroso: `wipe_and_resynthesize.py` ejecuta `DELETE` sobre tablas de memoria (`entities`, `entity_relations`, `concept_canonical`, `memory_processing_catalog`). No debe ejecutarse sin backup y aprobacion explicita.

Decision:

- No incorporarlos en bloque a `master`.
- Se confirmo que ninguna automatizacion ni ruta activa dependia de esos paths.
- El 2026-07-18 se movieron a `/home/maurol/dev/K-Chat-local-archive/untracked-20260718-015942`.
- El archivo conserva `MANIFEST.txt`, `SHA256SUMS.txt` y `RESTORE.sh`; la operacion es reversible.
- La copia de trabajo de la laptop quedo limpia y alineada con `origin/master`.
