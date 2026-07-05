# Handover: Pipeline de Memoria por Capas

**Creado:** 2026-07-04 22:00  
**Actualizado:** 2026-07-05 00:49 — Mauro + Debug Agent (opencode)  
**Propósito:** Que otro agente IA pueda continuar el laburo sin perder contexto.

---

## 1. Estado Actual Resumido

### Pipeline funcional y probado
El pipeline de memoria por capas corre **sin LLM** (extractivo puro) y produce artifacts en la **nueva estructura unificada**:

```
memory/
└── YYYY/
    └── MM/
        └── DD/
            ├── session--{channel}--{id}.md     ← Session summary
            ├── transversal.md                   ← Síntesis transversal
            ├── daily.md                         ← Síntesis diaria
            ├── candidates/
            │   ├── session_summary.jsonl        ← Candidatos de summaries
            │   └── transversal_synthesis.jsonl  ← Candidatos de transversal
            └── events/
                └── curation.md                  ← Reporte de curaduría
```

### Datasets generados (2026-07-05, corrida completa)
Todas las fechas con datos en la DB fueron procesadas exitosamente:

| Fecha | Sessions | Summaries | Candidatos | Transversal |
|---|---|---|---|---|
| 2026-06-15 | 4 | 4 | 13 (5 summary + 8 transversal) | 10 topics, 2 entidades |
| 2026-06-16 | 11 → 10 | 10 | 20 (12 summary + 8 transversal) | 12 topics, 4 entidades |
| 2026-06-18 | 1 (Telegram) | 1 | 13 (summary) | 0 topics |
| 2026-06-20 | 2 | 2 | 1 (summary) | 0 topics |
| 2026-07-03 | 3 | 3 | 21 (15 summary + 6 transversal) | 6 topics |
| 2026-07-04 | 3 → 2 | 2 | 25 (17 summary + 8 transversal) | 8 topics |
| **Total** | **24** | **22** | **93 candidatos** | **6 transversals** |

### Tests
```bash
20 passed in 15.34s
```
- `tests/unit/test_memory_repair.py` — 10 tests
- `tests/unit/test_transversal_synthesis.py` — 10 tests

### Estado git
- Branch: `master` (up to date with origin/master)
- 2 untracked files (`.kairos/server.pid`, `src/memory/synthesis/memory_inbox.py`)
- 0 modified files

---

## 2. Arquitectura del Pipeline (NUEVA estructura)

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

### Comando para correr todo (rápido, extractivo, sin LLM)
```bash
python scripts/generate_session_summaries.py \
  --date 2026-06-16 \
  --candidates --transversal --transversal-candidates \
  --daily-synthesis --curation-report --json
```

### Componentes modulares
```
src/memory/synthesis/
├── session.py       # Síntesis extractiva por sesión (keywords, metadata, first/last)
├── transversal.py   # Síntesis transversal entre sesiones (tokens repetidos)
├── daily.py         # Síntesis diaria (consume summaries + DB + embeddings/entities)
└── morning_plan.py  # Plan matinal (inbox + candidates + síntesis + git)

src/memory/maintenance/
├── audit.py         # Auditoría de vectores/catálogo (modo read-only)
└── repair.py        # Reparación planificada con dedup (--apply para mutar)

src/memory/paths.py  # ← CENTRAL: todas las rutas de la nueva estructura
```

### Pipeline outputs en vivo (ejemplo 2026-06-16)
```
memory/2026/06/16/
├── session--web--5b34d36f-588.md        ← Summary: "Injected Memories Inquiry"
├── session--web--0ff70e5c-da2.md        ← Summary: "Memory System Injection Status"
├── session--web--62778322-9ca.md        ← Summary: "Kairos AI Pet Design"
├── session--web--6d62c2ae-788.md        ← Summary: "GPT-5.5 Browser Extension"
├── ... (6 más)                           ← 10 summaries total
├── transversal.md                        ← 12 topics repetidos, 4 entidades
├── daily.md                              ← Síntesis diaria con previews
├── candidates/
│   ├── session_summary.jsonl             ← 12 candidatos
│   └── transversal_synthesis.jsonl       ← 8 candidatos
└── events/
    └── curation.md                       ← Reporte de corrida
```

---

## 3. Lo detectado / problemas encontrados

### ✅ Pipeline estable
- Corre en 1-3 segundos por fecha
- Idempotente (usa `content_hash` + `processing_catalog`)
- Sin LLM, 0 dependencias externas
- Filtra sesiones vacías automáticamente

### 🐛 Problemas detectados

#### 1. Sesiones de prueba ensucian los datos
Las sesiones `test-123`, `test-session-1781660948` aparecen en los summaries. Tienen 1 mensaje cada una. El pipeline las procesa igual. Habría que filtrarlas (por naming `test-*` o por `message_count < 2`).

#### 2. Sesiones que cruzan medianoche
La sesión `884d7680` se creó el 2026-07-03 23:58 pero tiene mensajes del 2026-07-04. Se procesa bajo su fecha de creación (07-03), lo cual es correcto, pero los mensajes del 07-04 no aparecen en la daily de esa fecha.

#### 3. Keywords code token filter incompleto
En 2026-07-04 aparecen keywords como `attempt`, `retry`, `assume`, `exists` que son palabras de código/debug, no conversacionales. El filtro `code_tokens` en `session.py` necesita expandirse.

#### 4. Telegram channel no tiene transversal con otros
La sesión de Telegram (2026-06-18) está aislada — nunca comparte fecha con sesiones web. El transversal da 0 topics porque es la única sesión de ese día.

#### 5. Memory inbox items legacy sin migrar
Hay 1 archivo en `memory/inbox/2026/07/04.jsonl` (estructura vieja) que la pipeline nueva no consume. Conviene migrarlo a `memory/2026/07/04/inbox.jsonl`.

#### 6. El archivo `HANDOVER_AGENTE_MEMORIA.md` original describía la estructura VIEJA
✅ Ya actualizado a la nueva estructura.

---

## 4. Lo que está verde / pendiente

### Prioridad alta
1. **Filtrar sesiones test** (`test-*`) en `session.py` antes de generar summary
2. **Mejorar keywords** — expandir `code_tokens` para filtrar `attempt`, `retry`, `error`, `connection`, `exists`, etc.
3. **Mejorar summaries extractivos** a LLM-based (usar deepseek v4 flash) cuando haya rate limit
4. **Migrar inbox legacy** de `memory/inbox/YYYY/MM/DD.jsonl` a `memory/YYYY/MM/DD/inbox.jsonl`
5. **Hacer commit** del estado actual (sin cambios modified, solo untracked)

### Prioridad media
6. **Probar `--embed`** para ver si el vector store responde con datos reales
7. **Generar plan matinal** con `daily_memory_report.py --preview --json`
8. **Revivir candidatos pendientes** (93 en total) con `review_recall_candidate action=promote_ready`
9. **Integrar más con `docs/ideas/curator-hybrid-retrieval.md`** — preguntas sintéticas, facetas, pesos vivos

### Prioridad baja
10. **Kairos "pensativo"** — triggers automáticos por contexto
11. **Célula Guardián semanal** — consistencia, merge de duplicados, poda
12. **Mejorar UI de revisión** — actualmente todo es CLI+artifacts

---

## 5. Sobre los AGENTS.md que gobiernan este agente

El agente debug (opencode) se rige por **dos** AGENTS.md:
- **Global**: `~/.config/opencode/AGENTS.md` — reglas base (test efficiency, execution style, response style)
- **Proyecto**: `K-Chat/AGENTS.md` — reglas específicas (arquitectura, memoria, tools, save_memory)

Ambos se inyectan en el system prompt al inicio. El del proyecto **extiende** al global, no lo reemplaza.

---

## 6. Próximo ciclo

Mauro va a iterar sobre los bugs detectados. Prioridades:
1. Filtrar sesiones test
2. Mejorar keywords filter
3. Probar `--embed` contra vector store real
4. Dejar pipeline corriendo estable

Cualquier duda sobre el diseño:
1. Leer `src/memory/paths.py` — estructura de rutas centralizada
2. Leer `docs/MEMORY_LAYERED_ROADMAP.md` — plan completo
3. Leer `docs/ideas/curator-hybrid-retrieval.md` — ideas de retrieval híbrido
4. Correr pipeline en una fecha chica para ver outputs fresh

---

## 7. Estructura de directorios (actualizada 2026-07-05)

```
memory/
├── 2026/06/15/            ← Pipeline outputs (4 sessions, 10 topics)
├── 2026/06/16/            ← Pipeline outputs (10 sessions, 12 topics) ← más completo
├── 2026/06/18/            ← Pipeline outputs (1 Telegram session)
├── 2026/06/20/            ← Pipeline outputs (2 sessions)
├── 2026/07/03/            ← Pipeline outputs (3 sessions)
├── 2026/07/04/            ← Pipeline outputs (2 sessions)
├── synthesis/2026/...     ← 🗄️ Legacy (no tocar, migrar eventualmente)
├── inbox/2026/...         ← 🗄️ Legacy (migrar a nueva estructura)
└── recall/2026/...        ← 🗄️ Legacy
```

```
scripts/
├── generate_session_summaries.py     ← Pipeline principal (✅ probado)
├── daily_memory_report.py            ← Reporte diario (no probado aún)
├── memory_audit.py                   ← Auditoría (remoto)
└── memory_repair.py                  ← Reparación (remoto)

src/memory/
├── synthesis/                        ← Generación de artifacts
│   ├── session.py                    ← Session summaries (extractivo)
│   ├── transversal.py                ← Cross-session synthesis
│   ├── daily.py                      ← Daily synthesis
│   └── morning_plan.py               ← Plan matinal
├── curator/                          ← Curaduría + candidatos
├── maintenance/                      ← Auditoría + reparación
├── retrieval/                        ← Búsqueda híbrida
└── paths.py                          ← 🎯 Central path computation
```

---

## 8. Contacto

Mauro va a estar iterando sobre los bugs detectados. Para cualquier duda:
- `src/memory/paths.py` define TODAS las rutas de la nueva estructura
- `scripts/generate_session_summaries.py --help` para flags
- La DB es `memory/kairos_memory.db` (40 sessions, ~3071 mensajes)
