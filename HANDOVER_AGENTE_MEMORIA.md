# Handover: Pipeline de Memoria por Capas

**Creado:** 2026-07-04 22:00 (actualizado 2026-07-04 22:30)  
**Autor:** Mauro + Codex (agente debug)  
**Propósito:** Que otro agente IA pueda continuar el laburo sin perder contexto.

---

## 1. Estado Actual Resumido

### Pipeline funcional
El pipeline de memoria por capas corre y produce artifacts en:
- `memory/session_summaries/{channel}/{session_id}.md`
- `memory/transversal/YYYY/MM/DD.md`
- `memory/synthesis/YYYY/MM/DD.md`
- `memory/candidates/YYYY/MM/DD.*.jsonl`
- `memory/inbox/YYYY/MM/DD.jsonl`
- `memory/events/curation/YYYY/MM/DD.md`
- `memory/plans/morning/YYYY/MM/DD.md` (via `daily_memory_report.py`)

### Datasets generados (reales)
- `memory/transversal/2026/07/02.md` — 0 sesiones (vacío)
- `memory/transversal/2026/07/03.md` — generado
- `memory/transversal/2026/07/04.md` — 0 sesiones (vacío)
- `memory/transversal/2026/06/17.md` — 5 sesiones, 57 mensajes
- `memory/synthesis/2026/06/17.md` — daily synthesis
- `memory/candidates/2026/06/17.session_summary.jsonl` — 2 candidatos
- `memory/candidates/2026/06/17.transversal_synthesis.jsonl`
- `memory/candidates/2026/06/27.session_summary.jsonl`
- `memory/inbox/2026/07/03.jsonl` — 2 items (de save_memory scope=inbox)
- `memory/events/curation/2026/06/17.md` y `2026/06/27.md`, `2026/07/03.md`, `2026/07/04.md`

### Tests pasan
```
20 passed in 15.34s
```
- `tests/unit/test_memory_repair.py` — 10 tests (repair planner + dedup + stale pruning + orphan cleanup)
- `tests/unit/test_transversal_synthesis.py` — 10 tests (transversal generation, candidates, embeddings, filtering, morning plan integration)

### Estado git
- Branch: `master` (up to date with origin/master)
- 3 modified files (sin commit): `generate_session_summaries.py`, `transversal.py`, `test_transversal_synthesis.py`
- Cambios: bugfix UTF-8, filtro metadata basura, política transversal más conservadora, tests nuevos

---

## 2. Arquitectura del Pipeline

### Script principal
```
scripts/generate_session_summaries.py
```
Flags disponibles:
| Flag | Función |
|---|---|
| `--date YYYY-MM-DD` | Fecha objetivo |
| `--embed` | Embedding de summaries |
| `--candidates` | Candidatos desde summaries |
| `--transversal` | Síntesis transversal |
| `--transversal-candidates` | Candidatos desde transversal |
| `--embed-transversal` | Embedding de transversal |
| `--embed-candidates` | Embedding de candidatos |
| `--embed-inbox` | Embedding de inbox items |
| `--daily-synthesis` | Síntesis diaria |
| `--curation-report` | Reporte de curaduría |
| `--json` | Output como JSON estructurado |

### Comando completo para correr todo
```bash
python scripts/generate_session_summaries.py \
  --date 2026-06-17 \
  --embed --candidates \
  --transversal --transversal-candidates --embed-transversal \
  --embed-candidates --embed-inbox \
  --daily-synthesis --curation-report --json
```

### Reporte diario
```bash
python scripts/daily_memory_report.py --preview --json
```
Lee candidates, inbox, síntesis, curaduría, git status, y genera plan matinal en `memory/plans/morning/YYYY/MM/DD.md`.

### Automatización programada
La tarea `plan-diario-kairos-k-chat` (en Codex) ejecuta cada día a las 09:00:
```
scripts/generate_session_summaries.py --embed --candidates --transversal
  --transversal-candidates --embed-transversal --embed-candidates
  --daily-synthesis --curation-report --json
scripts/daily_memory_report.py --preview --json
```

### Componentes modulares
```
src/memory/synthesis/
├── session.py       # Síntesis extractiva por sesión
├── transversal.py   # Síntesis transversal entre sesiones
├── daily.py         # Síntesis diaria (consume summaries y DB)
└── morning_plan.py  # Plan matinal (inbox + candidates + síntesis + git)

src/memory/maintenance/
├── audit.py         # Auditoría de vectores/catálogo (modo read-only)
└── repair.py        # Reparación planificada con dedup (--apply para mutar)
```

---

## 3. Lo que está verde / pendiente

### Calidad de summaries
Actualmente son **extractivos** (no LLM). Extraen keywords, metadata, first/last message. No hay resumen semántico real. Para mejorarlos hay que:
- Conectar con LLM (deepseek v4 flash) para generar resúmenes reales
- Guardar el resumen LLM como texto principal del artifact
- Mantener metadata extractiva como respaldo

### Cobertura de datos
- Solo hay sesiones reales en `2026-06-17` (5 sesiones) y `2026-06-27` (algunas más)
- El resto de los outputs están vacíos (transversal del 02/03/04 sin datos)
- Probar con más fechas: `--date 2026-06-27`, `--date 2026-06-18`, etc.

### Sesiones vacías
Muchas sesiones en la DB tienen `message_count=0`. El pipeline las procesa igual y genera summaries vacíos. Filtrar sesiones sin mensajes.

### Calidad de candidatos
- Los candidatos actuales son básicos: extraen keywords y señales simples
- No hay promoción automática a MEMORY.md (solo pending)
- `review_recall_candidate action=promote_ready` para promover candidatos listos

### Embeddings
- Los embeddings existen como pipeline, pero no se han generado realmente (no hay vector store con datos fresh en PC)
- Para probar embeddings se necesita vector store activo

---

## 4. Cómo probar

### Con fecha específica
```bash
python scripts/generate_session_summaries.py --date 2026-06-17 --json
```

### Rápido (solo summaries)
```bash
python scripts/generate_session_summaries.py --date 2026-06-17 --json
```

### Pipeline completo
```bash
python scripts/generate_session_summaries.py --date 2026-06-17 --embed --candidates --transversal --transversal-candidates --embed-transversal --embed-candidates --daily-synthesis --curation-report --json
```

### Corregir/actualizar
El pipeline es **idempotente**: si corres de nuevo con la misma fecha, no regenera artifacts que no cambiaron (usa `content_hash` + `processing_catalog`).

### Tests
```bash
python -m pytest tests/unit/test_transversal_synthesis.py -v --tb=short
python -m pytest tests/unit/test_memory_repair.py -v --tb=short
python -m pytest tests/unit/test_memory_audit.py -v --tb=short
```

---

## 5. Arquitectura "Lego" — Principios

Los módulos ya están separados con responsabilidades claras:
- **Synthesis**: genera artifacts (session, transversal, daily)
- **Curator**: consume artifacts y produce candidatos/relaciones
- **Maintenance**: audita y repara catálogos/vectores
- **Retrieval**: busca en capas

Reglas:
- No acoplar capas superiores desde inferiores (`src/tools/` no importa `src/core/`)
- No singletons globales — pasar dependencias como parámetros
- Los artifacts son el contrato: si generás algo nuevo, tiene que ser legible por `morning_plan`
- `curation_queue` centraliza la cola de acciones del curador

---

## 6. Para el próximo agente que tome esto

### Prioridad alta
1. **Correr pipeline con fechas reales** `--date 2026-06-27`, `--date 2026-06-20`, etc. para ver datos frescos
2. **Mejorar summaries extractivos** a LLM-based (usar deepseek v4 flash)
3. **Filtrar sesiones vacías** en `session.py` antes de generar summary
4. **Revivir candidatos pendientes** con `review_recall_candidate action=promote_ready`
5. **Hacer commit** de los 3 archivos modificados actuales

### Prioridad media
6. **Integrar más con `docs/ideas/curator-hybrid-retrieval.md`** — preguntas sintéticas, facetas, pesos vivos
7. **Probar embeddings** cuando haya vector store funcionando
8. **Mejorar UI de revisión** — actualmente todo es CLI+artifacts
9. **Guardar el plan** de las secciones conectadas (IDs por bloque, grafo relacional entre sesiones)

### Prioridad baja (ideas grandes)
10. **Kairos "pensativo"** — triggers automáticos por contexto sin necesidad de "recordá"
11. **RAM index rápido** para recall sin búsqueda pesada
12. **Célula Guardián semanal** — consistencia, merge de duplicados, poda

---

## 7. Estructura de directorios relevante

```
memory/
├── candidates/YYYY/MM/DD.*.jsonl     # Candidatos revisables
├── events/curation/YYYY/MM/DD.md     # Reportes de curaduría
├── inbox/YYYY/MM/DD.jsonl            # save_memory inbox
├── session_summaries/{channel}/      # Summaries por sesión
├── synthesis/YYYY/MM/DD.md           # Síntesis diaria
├── transversal/YYYY/MM/DD.md         # Síntesis transversal
├── plans/morning/YYYY/MM/DD.md       # Plan matinal (daily report)
├── kairos_memory.db                  # Memoria SQLite con vectores
└── kairos_curated_memory.db          # Memoria curada

scripts/
├── generate_session_summaries.py     # Pipeline principal
├── daily_memory_report.py            # Reporte diario
├── memory_audit.py                   # Auditoría (remoto)
└── memory_repair.py                  # Reparación (remoto)

src/memory/synthesis/                 # Generación de artifacts
src/memory/curator/                   # Curaduría + candidatos
src/memory/maintenance/               # Auditoría + reparación
src/memory/retrieval/                 # Búsqueda híbrida
```

---

## 8. Cosas que no están hechas (pero están documentadas)

- `docs/ideas/curator-hybrid-retrieval.md` — triggers, preguntas sintéticas, facetas, pesos vivos, spreading activation, célula guardián
- `docs/MEMORY_LAYERED_ROADMAP.md` — tiene TODO el plan detallado con fases, y marca qué está "aplicado" vs pendiente
- Telegram como canal completo (resumir sesiones de Telegram)
- Promoción automática conservadora (hoy es todo manual/pending)
- Workbench visual (hoy es tool-only)
- `docs/archive/laptop-stash-audit/README.md` — auditoría de stashes de laptop preservados

---

## 9. Configuración del entorno

- Python: `C:\Users\mauro\AppData\Local\Programs\Python\Python313\python.exe`
- `.venv` es un archivo (no directorio) que apunta a `/home/maurol/dev/K-Chat/venv` (Linux)
- En Windows correr con python directo (sin .venv)
- DB de memoria: `memory/kairos_memory.db`
- DB de sesiones: la que resuelve `resolve_db_path()` (configurable)
- Variable de entorno: `KAIROS_MEMORY_DB_PATH` para override

---

## 10. Cambios aplicados en sesión 2026-07-04 22:00

### Fix: Filtrar sesiones vacías (session.py)
- `generate_session_summaries()` ahora salta sesiones con `message_count == 0`
- Antes generaba summaries vacíos que ensuciaban el pipeline
- Archivo: `src/memory/synthesis/session.py` — `if not messages: continue`

### Fix: Keywords sin ruido de código (session.py)
- `_keywords()` ahora solo extrae de mensajes de usuario (no de código del assistant)
- Filtra tokens de código: none, import, self, return, logger, async, await, etc.
- Archivo: `src/memory/synthesis/session.py`

### Fix: Daily synthesis sin sesiones vacías (daily.py)
- `generate_daily_synthesis()` ahora oculta sesiones con 0 mensajes en la sección Sessions
- Muestra contador: "X with messages (Y total)"
- Archivo: `src/memory/synthesis/daily.py`

### Fix: Evidencia duplicada en transversal (transversal.py)
- `build_transversal_synthesis()` ahora usa `seen_token_evidence` por token, no global
- Antes la misma evidencia se mostraba duplicada para el mismo token
- Archivo: `src/memory/synthesis/transversal.py`

### Pipeline regenerado
- 2026-06-17: 2 sesiones (eran 5, 3 vacías filtradas) — transversal con 3 topics
- 2026-06-27: 1 sesión de 115 mensajes — summary con keywords conversacionales
- 2026-06-27: 1 sesión de 115 mensajes — summary con keywords conversacionales

### Tests
- 20/20 tests pasan (memory_repair + transversal_synthesis)
- Sin commits, sin push, 4 archivos modificados localmente

## 11. Contacto / Próximo ciclo

Mauro va a estar iterando sobre este pipeline unos días hasta que vuelva Codex. Las prioridades son:
1. Probar pipeline con fechas reales
2. Mejorar summaries (extractivo → LLM)
3. Filtrar sesiones vacías
4. Promover candidatos pendientes
5. Dejar todo commiteado y sincronizado para el próximo "Codex day"

Cualquier duda sobre el diseño, leer `MEMORY_LAYERED_ROADMAP.md` primero, después `docs/ideas/curator-hybrid-retrieval.md`. La arquitectura base ya corre y está testeada.
