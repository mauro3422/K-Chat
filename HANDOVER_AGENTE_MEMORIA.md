# Handover: Pipeline de Memoria por Capas

**Creado:** 2026-07-04 22:00  
**Actualizado:** 2026-07-09 20:30 — Test completo del LLM curator + fixes críticos  
**Propósito:** Que otro agente IA pueda continuar el laburo sin perder contexto.

---

## 1. Estado Actual Resumido

### Continuación 2026-07-11 — síntesis conceptual y gates de promoción

- ✅ `daily.md` queda como reporte operativo; la nueva `conceptual.md` contiene
  panorama, temas, decisiones, hechos, preguntas, próximos pasos y candidatos
  con evidencia/confianza generados por LLM.
- ✅ El prompt conceptual excluye métricas, scores, IDs, rutas, saludos, retries
  y ruido de herramientas; prohíbe inventar causalidad o estados de cierre.
- ✅ Días sin actividad se marcan explícitamente y no llaman al LLM.
- ✅ La transversal ya no convierte metadata de scoring (`blended`, `coherence`,
  `1.00`, LSA/PMI) en temas y guarda fuentes portables por nombre de archivo.
- ✅ La regeneración transversal compara también el hash del archivo real; el
  catálogo ya no puede ocultar un artifact viejo o contaminado.
- ✅ Confianza estadística alta ahora significa `review`; la autopromoción queda
  bloqueada con `human_benchmark_required` hasta calibración humana aprobada.
- ✅ `save_memory` deduplica retries exactos con la misma procedencia, sin perder
  refuerzos legítimos provenientes de otro mensaje o sesión.
- ✅ Pruebas focales nuevas para síntesis conceptual, días vacíos y filtrado de
  metadata; 67 pruebas del flujo ampliado pasan.
- ✅ Reprocesamiento histórico completo sobre la DB importada de Linux:
  30 sesiones / 3.233 mensajes, 9 fechas entre 2026-06-15 y 2026-07-04.
  Todas las fechas tienen `daily.md`, `transversal.md` y `conceptual.md`; las
  sesiones test/vacías continúan excluidas por política.
- ✅ El batch histórico reutiliza un único scorer inyectado en vez de reconstruir
  TF-IDF/BM25/grafo/PMI por cada fecha.
- ✅ Integración LLM conceptual corregida para el contrato real de `chat()`
  (`response.message.content/reasoning_content`), razonadores que devuelven JSON
  con saltos escapados y fallback/reintento del proveedor.
- ✅ Segunda pasada de calidad conceptual: jerarquía explícita de evidencia
  (usuario/tool/artifact/multifuente > asistente > inferencia), clasificación de
  durabilidad y validador post-LLM. Se rechazan afirmaciones del asistente,
  inferencias, claves no canónicas, métricas/versiones, deadlines vencidos,
  condiciones transitorias, probes y detecciones triviales de entidad/idioma.
- ✅ Los headings históricos ya dicen "registradas ese día" / "para esa fecha"
  para impedir que planes o estados viejos se interpreten como actuales.
- ✅ Las 9 síntesis fueron regeneradas y leídas semánticamente. Los falsos
  candidatos de Linux, unicidad de mercado, identidad trivial y métricas antiguas
  quedaron eliminados. Suite focal final: 63 pruebas pasando.
- ✅ `conceptual.json` persiste la salida estructurada y
  `conceptual.status.json` registra `current`/`generation_failed`, error y si se
  preservó el último Markdown válido. Los timeouts ya no destruyen el resultado.
- ✅ Las 9 síntesis conceptuales fueron embebidas como
  `source=conceptual_synthesis` mediante identidad de pipeline propia.
- ✅ Primer dataset supervisado delegado: 8 candidatos, 3 promote, 4 reject y
  1 defer. Benchmark baseline F1=0.60; filtro automático por overlap F1=0.40.
  Conclusión: overlap sirve como alerta, no como gate; autopromoción sigue OFF.
- ✅ El overlap ahora es riesgo graduado (`low`, `medium`, `high`) con
  recomendación `review`; ya no descarta candidatos buenos por sí solo.
- ✅ Cola accionable generada en `memory/curator-review-queue.jsonl` con
  candidate_id estable, overlap, riesgo y vigencia de bugs.
- ✅ Auditoría de bugs conservadora: sólo marca `resolved` con un marcador
  explícito de cierre; el resto queda `open_or_unverified` y requiere revisión
  de código.
- ✅ El script `build_curator_review_queue.py` permite regenerar esa cola.
- ⚠️ El proveedor LLM sigue fallando para 2026-06-16 después de varios retries;
  `conceptual.status.json` registra `generation_failed` y preserva el Markdown
  previo. Es un problema externo de disponibilidad, no una pérdida de datos.

### Cierre técnico de esta pasada

- ✅ La cola conceptual se puede regenerar desde el CLI con
  `--curator-review-queue` y queda visible para el curator workbench/dashboard.
- ✅ La vectorización conceptual usa identidad propia, catálogo idempotente y
  `VectorStore` real; los reintentos no duplican embeddings.
- ✅ Confidencias LLM inválidas se rechazan como `invalid_confidence` sin abortar
  toda la síntesis.
- ✅ Daily y conceptual comparten una única fecha objetivo y reportan errores
  separados; el filtro transversal sólo descarta líneas metadata completas.
- ✅ La deduplicación del inbox inspecciona todo el histórico cuando necesita
  verificar un retry con provenance explícita.

### Continuación 2026-07-10 (Windows + laptop)

- ✅ `curate --help` ya usa `argparse` y no ejecuta mantenimiento por accidente.
- ✅ Las pruebas de síntesis escriben sólo dentro de `tmp_path`; se regeneraron
  los reportes reales contaminados y el preflight local quedó sin inconsistencias.
- ✅ Caché ONNX de Windows reparado; fastembed genera vectores 384D no nulos y
  el benchmark híbrido devolvió señales vectoriales reales entre 30 % y 68 %.
- ✅ La cola deduplica copias históricas por `candidate_id`: pasó de 4 acciones
  repetidas a 1 candidato único en el plan del 2026-07-10.
- ✅ El repair plan detecta vectores de sesiones eliminadas y evita usarlos como
  fuente de deduplicación.
- ⚠️ Benchmark A/B real bloqueado explícitamente con
  `no_matching_human_decisions`: no hay decisiones humanas persistidas en
  Windows ni en la laptop.
- ✅ El curador de sesiones ya no inyecta los primeros 3.000 caracteres fijos de
  `MEMORY.md`: recupera memoria canónica relevante por sesión mediante búsqueda
  híbrida y usa fallback léxico cuando no hay vectores adecuados.
- ✅ El retrieval del curador exige evidencia léxica o de entidad, limita el
  contexto a tres resultados / 3.000 caracteres y eliminó falsos positivos
  vectoriales observados durante la prueba cruzada.
- ✅ Las extracciones aceptadas se mantienen como contexto provisional durante
  la misma tanda, por lo que las sesiones siguientes conocen lo ya detectado
  antes de escribir en el inbox.
- ✅ El contrato LLM quedó estricto, con temperatura `0.0`, máximo cuatro hechos,
  claves kebab-case y categorías cerradas. El filtro rechaza categorías ajenas y
  variantes triviales de nombre de usuario.
- ✅ Prueba controlada PC/laptop: el contexto relevante evitó reextraer
  `bugs.md` en 4/4 ejecuciones; el contexto enfocado bajó de 9.449 a 4.968
  caracteres. Los microcortes aparecieron en ambos nodos, confirmando que son
  variación del proveedor/fallback y no una falla exclusiva de la laptop.
- 🔜 Antes de etiquetar: ampliar la sonda contextual a 10–20 sesiones, registrar
  modelo efectivo/reintentos por llamada y confirmar que la reducción de
  duplicados se mantiene con mayor muestra.

### Continuación 2026-07-09 (Windows)

- ✅ Filtro de sesiones de prueba endurecido: solo prefijos explícitos
  (`test-`, `test_`, `smoke-test-`), sin descartar IDs legítimos como
  `contest-*`; también se omiten sesiones con menos de 2 mensajes.
- ✅ Deduplicación post-extracción del curator por clave y similitud textual,
  tanto dentro de una corrida como contra entradas pendientes del inbox.
- ✅ Filtro de entradas triviales de identidad (`user:name` y equivalentes).
- ✅ Inbox legacy migrado: no quedan archivos bajo `memory/inbox/`; el dato
  vigente está en `memory/2026/07/04/inbox.jsonl`.
- ✅ `CuratorAgent` y benchmark A/B creados en
  `src/memory/curator/{agent,benchmark}.py`, reutilizando decisiones y scorer
  inyectados; calcula precision, recall y F1.
- ✅ 48 pruebas focales pasan para síntesis, curator, filtros y benchmark.

Pendiente inmediato: ejecutar el benchmark con decisiones humanas reales,
probar embeddings/fastembed en el venv de producción y correr el plan matinal.

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

---

## 2.5. LLM Curator — Test de calidad (2026-07-09)

Se corrió el LLM curator (`deepseek-v4-flash`) sobre 20 sesiones. Resultado completo en `docs/curator-quality-test-2026-07-09.md`.

### Resumen
- **14/20 sesiones** produjeron extracciones (~50 entradas total)
- **Bugs detectados con alta precisión**: `get_tool_history async sin await`, `extract_text return prematuro`, `db_query column validation`, `delete memory value vacío`, etc.
- **Decisiones y visión capturadas**: inyección automática hasta umbral, memoria "viva" mid-reasoning, pesos sinápticos, LAN multi-device
- **Fechas correctas**: fix de `CURRENT DATE` en system prompt eliminó alucinaciones de año

### Bugs arreglados en el pipeline
| Bug | Fix | Archivo |
|-----|-----|---------|
| LLM sin tokens (razonamiento consume todo) | `max_tokens` 1024→16384 | `curate.py:71` |
| Failover cascada (1 solo modelo) | + `deepseek-v4-flash-free` | `config_loader.py:23` |
| 5 min bloqueo por timeout | `MODEL_FAIL_TTL` 300→60s | `model_state.py:17` |
| Crash si único modelo falla | try-except → FALLBACK_MODEL | `client.py:47,171` |
| Entry point nocturno roto | `_save_memory_local` → `_save_memory_inbox_local` | `.kairos/curator.py:17` |
| LLM alucinaba años | `CURRENT DATE` en system prompt | `curate.py:25,43` |
| Corría con python del sistema | Usar `./venv/bin/python` | `.kairos/curator.py` |

### Cómo repetir
```bash
cd /home/maurol/dev/K-Chat && source venv/bin/activate
sqlite3 memory/kairos_curated_memory.db \
  "DELETE FROM memory_processing_catalog WHERE stage='curated';"
python -m src.memory.curator.curate
```

### Calidad
- ⭐⭐⭐⭐⭐ Bugs: raíz exacta, código referenciado
- ⭐⭐⭐⭐ Decisiones: contexto y razón claros
- ⚠️ Redundancia: mismo bug en 3+ sesiones (falta dedup semántico)
- ⚠️ ~15% timeouts API (OpenCode Go micro-cortes)

---

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
1. ✅ **Filtrar sesiones test** (`test-*`) en `session.py` antes de generar summary
2. ✅ **Mejorar keywords** — extracción prioriza mensajes del usuario y usa STOP consolidado
3. **Mejorar summaries extractivos** a LLM-based (usar deepseek v4 flash) cuando haya rate limit
4. ✅ **Migrar inbox legacy** de `memory/inbox/YYYY/MM/DD.jsonl` a `memory/YYYY/MM/DD/inbox.jsonl`
5. ✅ **Deduplicar y filtrar salidas del curator** antes de escribir el inbox

### Prioridad media
6. ✅ **`--embed` validado** con fastembed 384D y búsquedas híbridas reales
7. ✅ **Plan matinal generado** con preflight local sano y health remoto
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

Mauro va a iterar sobre los bugs detectados por el LLM curator. Prioridades:
1. ✅ Filtrar sesiones test sin falsos positivos por substring
2. ✅ Mejorar keywords filter
3. ✅ **LLM curator probado** — 50 extracciones de 14/20 sesiones, bugs detectados con precisión
4. ✅ **Fixes críticos aplicados** — max_tokens, PRIORITY_MODELS, MODEL_FAIL_TTL, entry point nocturno, CURRENT DATE
5. ✅ **Deduplicación semántica** post-extracción — dentro de corrida e inbox pendiente
6. ✅ **Filtro de entradas triviales** — user:name y similares no aportan valor
7. ✅ **`fastembed` verificado en ambos entornos** — laptop con `fastembed 0.8.0`
8. **Correr benchmark A/B real** con decisiones humanas y persistir pesos aprobados

Cualquier duda sobre el diseño:
1. Leer `src/memory/paths.py` — estructura de rutas centralizada
2. Leer `docs/MEMORY_LAYERED_ROADMAP.md` — plan completo
3. Leer `docs/curator-quality-test-2026-07-09.md` — resultados del test LLM curator
4. Leer `docs/ideas/curator-hybrid-retrieval.md` — ideas de retrieval híbrido
5. Correr `python -m src.memory.curator.curate --dry` para ver el pipeline sin LLM

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
