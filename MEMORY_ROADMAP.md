# 🧠 K-Chat Memory Architecture — Roadmap

> Documento de planificación para el sistema de memoria multicapa de K-Chat.
> Creado: 2026-06-12 | Actualizado: 2026-06-16 — v0.0.57+

---

## 📐 Estado Actual (v0.0.57+) — Post-Refactor

```
✅ MEMORY.md — source of truth, texto plano, inyectado en system prompt
✅ save_memory — escribe MEMORY.md + memory.db + embedding simultáneamente
✅ memory.db (global) — memory_index + sqlite-vec + clusters + relaciones
✅ sessions.db (local) — mensajes crudos, tools, widgets por sesión
✅ Embeddings — fastembed multilingual (384 dims, ~80MB RAM)
✅ Vector store — sqlite-vec con KNN search, filtro por source, metadata
✅ FASE 7 completa — keywords TF-IDF + noise filter + clustering + relations
✅ FASE 7 pipeline integrado — vectorize_sessions.py end-to-end
✅ Migraciones formales — vec_entries, vec_meta, topic_clusters,
│                       exchange_clusters, topic_relations con FKs e índices
✅ DI completo — VectorStore en MemoryRepositories, tools lo reciben via _repos
✅ Session hook — vectorización automática al cerrar sesión
✅ Type safety — _repos.memory tipado como MemoryRepositories
✅ Curator desacoplado — sin paths hardcodeados, sin upward imports
✅ manage_memory clusters|topics — operaciones implementadas
✅ recall_memories — búsqueda semántica en memory + session
✅ deleted_sessions.db — sesiones eliminadas migran con embedding + metadata
✅ db_query — 11 tablas, ruteo automático a sessions/memory/deleted
```

---

## 🔬 Referencias del Ecosistema

### Mem0 (58.7k ⭐) — `mem0ai/mem0`
**"Universal memory layer for AI agents"** — Y Combinator S24, Apache 2.0.
Paper: https://mem0.ai/research | Benchmarks: 92.5 LoCoMo, 94.4 LongMemEval

**Arquitectura:**

```
Messages → LLM Extraction → Batch Embed → Vector Store → Entity Store
                                     ↓                          ↓
                              SQLite History ←── Hybrid Retrieval (semantic + BM25 + entity)
```

**Pipeline de add() — V3 Phased Batch (Abril 2026):**

| Fase | Qué hace | Equivalente K-Chat |
|------|----------|--------------------|
| 0 | Context gathering (últimos mensajes) | N/A (nosotros tenemos sesiones completas) |
| 1 | Existing memory retrieval (vector search top-10) | recall_memories |
| 2 | **LLM additive extraction**: prompt único extrae facts | Curator LLM (FASE 6) |
| 3 | Batch embed de todos los textos extraídos | generate_embeddings_batch |
| 4 | CPU processing + hash dedup | N/A (nosotros no deduplicamos aún) |
| 5 | Hash dedup dentro del batch | N/A |
| 6 | **Batch persist** en vector store | VectorStore.insert |
| 7 | **Batch entity linking**: extract → embed → search → upsert | ❌ No implementado |
| 8 | Save messages + telemetry + return | save_messages |

**Multi-signal retrieval (lo más relevante para nosotros):**

```
Query
  ├── Semantic similarity (embedding → vector KNN)
  ├── BM25 keyword matching (texto lematizado → score)
  └── Entity matching (entidades extraídas → entity store search)
       └── Fused score → ranked results
```

**Entity store:** Colección vectorial separada con `linked_memory_ids` que vinculan cada entidad a las memorias que la mencionan. Tipos de entidades: persona, tecnología, proyecto, lugar, etc.

**Lecciones de Mem0:**
- La extracción de entidades + linking es parte del pipeline de `add()` — no un paso separado
- El retrieval híbrido (3 señales fusionadas) es lo que da el salto de calidad
- El hash dedup es barato y evita memorias duplicadas
- Batch operations (embed, search, insert) son clave para performance

### Letta / MemGPT (23.4k ⭐) — `letta-ai/letta`
**"Platform for stateful agents"** — Apache 2.0, Python.

Menos relevante para infraestructura de memoria, más orientado a:
- Stateful agents con memoria por bloques (human, persona)
- Self-improving agents con autoevaluación
- No tiene entity graph ni retrieval híbrido como Mem0

### Diferencias clave con K-Chat

| Aspecto | Mem0 | K-Chat |
|---------|------|--------|
| Capa de memoria | 1 capa (vector store + SQLite) | 3 capas (texto + SQLite + raw sessions) |
| Source of truth | Vector store | MEMORY.md (reconstruye el store) |
| Entity extraction | Sí, batch en add() | ❌ No implementado |
| Hybrid retrieval | Semantic + BM25 + entity | Semantic only (vector) |
| Topic clustering | No | Sí (Jaccard + TF-IDF) |
| LLM extraction | Sí, en cada add() | Sí, en curator nocturno |
| Sync multi-device | Cloud/server | Syncthing + MEMORY.md como source of truth |
| Curator autónomo | No | Sí (células de memoria planeadas) |
| Keywords | BM25 (lematizado) | TF-IDF puro |

**Conclusión:** K-Chat tiene una arquitectura más completa en algunas dimensiones (3 capas, clustering, curator, sync), pero le falta entity graph y hybrid retrieval que Mem0 ya demostró que dan el salto de calidad.

---

## 🗺️ Roadmap por Fases (Actualizado 2026-06-16)

### ✅ FASE 0 — Setup (COMPLETADO)
```
pip install fastembed sqlite-vec
src/memory/embeddings/service.py    ← generate_embedding() + batch
src/memory/vector/store.py          ← VectorStore con insert/search/delete/count
```

### ✅ FASE 7 — Etiquetado Heurístico y Clustering (COMPLETADO)
```
src/memory/keywords/extractor.py     ← TF-IDF custom
src/memory/noise_filter.py           ← Heurístico (longitud, tools, saludos)
src/memory/clustering/heuristic.py   ← Jaccard similarity + merge
src/memory/clustering/relations.py   ← Shared keywords → relations
Integración en vectorize_sessions.py ← Pipeline end-to-end
manage_memory clusters|topics        ← Tools implementadas
Migraciones formales                 ← Vecinos + clusters en memory_schema.py
```

### 🔄 FASE 2 — Entity Graph (PRÓXIMA — Semana 1)

**Objetivo:** Extraer entidades de las sesiones y construir un grafo relacional.

**Basado en Mem0 Phase 7:** Batch entity extraction + linking + store.

```
[ ] Migration 004 — Tabla entities:
    CREATE TABLE entities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        entity_type TEXT NOT NULL,       -- persona, proyecto, tecnologia, tema, lugar
        metadata TEXT DEFAULT '{}',      -- JSON con atributos extra
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        mention_count INTEGER DEFAULT 1,
        embedding_id INTEGER REFERENCES vec_meta(rowid)  -- nullable, embedding de la entidad
    );

[ ] Migration 005 — Tabla entity_relations:
    CREATE TABLE entity_relations (
        source_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        relation_type TEXT NOT NULL,     -- usa, crea, menciona, relacionado_a, depende_de
        weight REAL DEFAULT 1.0,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        PRIMARY KEY (source_id, target_id, relation_type)
    );

[ ] src/memory/entity/extractor.py
    → Extrae entidades del texto de exchanges (regex + heurístico)
    → Tipos: persona, proyecto, tecnologia, tema, lenguaje
    → Sin LLM (como FASE 7) — extracción puramente heurística
    → Integrado en vectorize_sessions.py (Fase 7.5 en el pipeline)

[ ] src/memory/entity/linker.py
    → Batch link: para cada entidad extraída, buscar si ya existe (por nombre + tipo)
    → Si existe: actualizar last_seen + mention_count
    → Si no: insertar nueva entidad + generar embedding del nombre
    → Detectar relaciones: si dos entidades aparecen en el mismo exchange → crear/fortalecer arista

[ ] Tool: search_entities(query, type=None, limit=10)
    → Buscar entidades por nombre o similitud semántica
    → Devolver entidades + metadatos (menciones, primera/última vez)

[ ] Tool: explore_graph(entity_id, depth=2)
    → CTE recursivo para traversal del grafo
    → "dame todo lo conectado a X hasta profundidad 3"

[ ] Integrar en vectorize_sessions.py:
    → Por exchange: keywords → noise filter → embed → cluster → extract entities → link entities

Pipeline FASE 2 completo:
```
Exchange → TF-IDF → Noise filter → Embed → Cluster → [NUEVO] Extract entities → Link entities
                                                                      ↓
                                                          entities + entity_relations tables
```

#### Arquitectura del Entity Graph

```
entities                          entity_relations
┌─────────────────────┐          ┌──────────────────────────┐
│ id: UUID (PK)       │          │ source_id (FK→entities)  │
│ name: "Kairos"      │◄─────────┤ target_id (FK→entities)  │
│ type: "proyecto"    │    FK    │ relation_type: "crea"    │
│ metadata: {...}     │          │ weight: 5                │
│ mention_count: 42   │          │ first_seen / last_seen   │
│ first/last_seen     │          └──────────────────────────┘
│ embedding_id (FK)   │
└─────────────────────┘
```

#### Ejemplos de entidades que se extraerán

| Texto del exchange | Entidades extraídas |
|--------------------|--------------------|
| "Mauro agregó async tools a K-Chat" | mauro(persona), K-Chat(proyecto), async tools(tecnologia) |
| "El fix de CSP en app_factory.py" | CSP(tecnologia), app_factory.py(proyecto) |
| "Hablando de survivorOS y Rust" | survivorOS(proyecto), Rust(lenguaje) |

---

### 🔄 FASE 3 — Retrieval Híbrido (Semana 2-3)

**Objetivo:** Combinar 3 señales de búsqueda como Mem0: vector + keywords + entidades.

```
[ ] HybridRetriever class en src/memory/retrieval/
    → Input: query del usuario
    → 3 scoring passes en paralelo:
        1. Vector search (semántico) — sqlite-vec KNN → score
        2. Keyword matching — TF-IDF sobre keywords del exchange → score
        3. Entity matching — extraer entidades de la query → buscar en entity graph → score
    → Fuse: weighted sum de los 3 scores
    → Reranking por relevancia temporal (más reciente = peso extra)

[ ] Token budget management
    → Calcular tokens disponibles en context window
    → Priorizar resultados por fused score
    → Truncar si excede límite

[ ] Inyección en system prompt
    → Bloque "## Relevant Past Memories" auto-generado
    → Solo aparece si hay memorias relevantes (fused score > threshold)
    → Incluye: memoria + source + timestamp + entidades relacionadas

[ ] Tests: 7+ tests para el retriever híbrido
    → Vector search alone vs hybrid search (calidad)
    → Token budget truncation
    → Temporal reranking
```

**Arquitectura del retriever (basada en Mem0):**
```
Query
  │
  ├→ Embedding ──→ Vector KNN ──→ semantic_score
  │
  ├→ TF-IDF ─────→ Keyword match ──→ keyword_score
  │
  └→ Entity ext. ─→ Entity search ──→ entity_score
       │               │
       └── entities ───┘ linked_memories
  │
  Fuse(semantic, keyword, entity) → ranked results
  │
  Temporal reranking
  │
  Token budget → inject into system prompt
```

---

### 📐 FASE 3.5 — Inyección Inteligente en System Prompt (Semana 3)

**Objetivo:** Que el agente reciba memorias relevantes automáticamente sin usar tools.

```
[ ] build_system_prompt() modificado:
    → Antes de armar el prompt, calcular embedding del último mensaje
    → HybridRetriever.search(query_embedding + keywords + entities)
    → Top-5 resultados → formato "## Relevant Past Memories"
    → Inyectar SOLO si hay memorias con fused score > 0.5
    → Cache: no re-buscar si el mensaje es similar al anterior

[ ] Formato de inyección:
    ## Relevant Past Memories
    The following information from past conversations may be relevant:

    [memory] Sobre el fix de CSP: se agregó unsafe-inline a script-src
             (source: memory, last: 2026-06-15, entities: CSP, app_factory.py)

    [session] Hablando de survivorOS y su motor gráfico en C++
              (source: session 3 days ago, entities: survivorOS, C++)

[ ] Control de tokens:
    → Si el budget es bajo: solo top-3, sin entity context
    → Si hay espacio: top-5 + entidades relacionadas
    → Máximo 15% del context window para memorias

[ ] Prerequisito: HybridRetriever funcionando (FASE 3)
```

---

### 📐 FASE 2.5 — Hash Dedup (Semana 2, paralelo con FASE 3)

**Objetivo:** Evitar memorias duplicadas en el vector store (inspirado en Mem0 Phase 4-5).

```
[ ] src/memory/dedup.py
    → Hash MD5 del texto completo de cada exchange
    → Al vectorizar: check si el hash ya existe en vec_meta
    → Si existe: skip (no guardar duplicado)
    → Si no existe: guardar + almacenar hash en metadata

[ ] Migration: agregar columna hash a vec_meta (o ya está en metadata JSON)
    → Check si metadata ya tiene campo hash → si no, migrar

[ ] Integrar en vectorize_exchange():
    → Calcular hash antes de embed
    → Check existente por hash + source + source_key
    → Si duplicado: return None (sin gastar embedding)
```

---

### 🔄 FASE 6 — Células de Memoria (Background Curator) — Semana 4

**Objetivo:** Agentes autónomos que curan, conectan y optimizan la memoria post-sesión.

**Diferencias con Mem0:** Mem0 hace LLM extraction en cada `add()` (inline). Nosotros lo hacemos offline (nocturno) porque:
- No gastamos tokens por cada mensaje
- Podemos procesar lotes (más eficiente)
- El curador puede ver el panorama completo (clusters + relaciones)

```
[ ] Session Miner — lee sesiones del día, extrae insights → save_memory
[ ] Entity Extractor — extrae entidades → grafo (FASE 2)
[ ] Cross-Session Tracer — detecta patrones entre sesiones
[ ] Memory Gardener — poda duplicados, fusiona similares (FASE 4)
[ ] Orchestrator — lanza células en paralelo, gestiona resultados
[ ] Systemd timer o cron para ejecución diaria
```


### 📐 FASE 4 — Consolidación de Memoria (Poda + Fusión) — Post-FASE 6

**Objetivo:** Mantener la memoria limpia sin LLM. Eliminar ruido, fusionar duplicados, archivar lo obsoleto.

**Estrategia heurística (sin LLM):**
```
[ ] Fusión por embeddings similares > 0.95
    → Dos keys que apuntan al mismo concepto se fusionan automáticamente
    → El value se combina preservando ambos timestamps
[ ] Archivo por obsolescencia
    → Keys con score de consulta bajo por N días → movidas a sección Archived en MEMORY.md
    → NO se borran — se marcan como archived para preservar datos
[ ] Dedup por contenido
    → Si dos keys tienen values con >90% overlap de palabras, fusionar
    → La key más genérica sobrevive, la específica se archiva
[ ] Memory Gardener (desde FASE 6)
    → La célula Gardener ejecuta estas reglas periódicamente
```
**Integración:** Corre como parte de FASE 6 (célula Gardener), no como proceso separado.

---

### 📐 FASE 5 — Proactividad (Futuro lejano)

**Objetivo:** Kairos inicia conversaciones, no solo responde.

**Idea conceptual:**
```
[ ] Sistema de "daily técnica"
    → Kairos asigna una lectura de 5-10 min/día al usuario
    → Un archivo del proyecto K-Chat explicado desde abajo
    → Ideal para leer en el bondi
[ ] Widget de estudio interactivo
    → Visualizaciones animadas de conceptos (buses, datos, hardware)
    → Skill especial de widgets educativos
[ ] Disparador por tiempo
    → Si pasan X horas sin actividad, Kairos manda un ping con data útil
```
**⚠️ Sin diseño concreto todavía.** Requiere repensar push vs pull en los canales. Se define cuando el sistema base esté sólido.

---

## 📊 Comparativa de Arquitecturas

| Feature | Mem0 | Letta/MemGPT | K-Chat (hoy) | K-Chat (target) |
|---------|------|--------------|--------------|-----------------|
| Vector search | ✅ Qdrant/FAISS/etc | ✅ | ✅ sqlite-vec | ✅ |
| Keyword search | ✅ BM25 | ❌ | ✅ TF-IDF | ✅ |
| Entity graph | ✅ | ❌ | ❌ | 🔄 FASE 2 |
| Hybrid retrieval | ✅ (3 signals) | ❌ | ❌ (vector only) | 🔄 FASE 3 |
| Topic clustering | ❌ | ❌ | ✅ Jaccard | ✅ |
| LLM extraction | ✅ inline (cada add) | ❌ | ✅ offline (curator) | ✅ |
| Hash dedup | ✅ | ❌ | ❌ | 🔄 FASE 2.5 |
| Temporal reasoning | ✅ | ❌ | 🟠 timestamps | 🔄 FASE 3 |
| Cross-session | 🟠 partial | ❌ | ✅ | ✅ |
| Memory blocks | ❌ | ✅ | N/A | N/A |
| Source of truth | Vector store | Agent state | MEMORY.md | MEMORY.md |
| Sync multi-device | Cloud | Cloud | Syncthing | Syncthing |
| Open source | ✅ Apache 2.0 | ✅ Apache 2.0 | ✅ | ✅ |

---

## 📦 Decisiones Técnicas (Actualizadas)

| Decisión | Opción elegida | Por qué |
|----------|---------------|---------|
| Vector DB | **sqlite-vec** | Misma DB que ya usamos, 0 servers extra |
| Embeddings | **paraphrase-multilingual-MiniLM-L12-v2** | ~80MB RAM, multilingual, 384 dims |
| Keyword extraction | **TF-IDF custom** | Cero dependencias extra, milisegundos |
| Topic clustering | **Jaccard similarity** | Sin LLM, determinístico, rápido |
| Entity extraction | **Heurística** → futuro LLM | Como FASE 7: primero heurístico, después LLM opcional |
| Entity store | **Misma DB sqlite-vec** (source="entity") | Evita otra dependencia, mismo patrón vec_meta |
| Hybrid scoring | **Weighted sum** | Simple, eficaz, ajustable por pesos |
| Session scope | **user_id/agent_id** (como Mem0) | Filtro por sesión en queries |
| Hash dedup | **MD5 del texto** | Barato, sin dependencias |
| Curator trigger | **Background task post-sesión** → futuro cron | No bloquea el stream |

---

## 📊 Métricas de Éxito

- [ ] **FASE 2**: Entity extraction >80% precision en proyectos y tecnologías
- [ ] **FASE 3**: Hybrid retrieval supera a vector-only en 15%+ en recall@5
- [ ] **FASE 3.5**: Inyección en system prompt sin exceder 15% del context window
- [ ] **FASE 2.5**: Cero duplicados en vector store (verificado por hash)
- [ ] **Global**: El asistente recuerda información entre sesiones sin usar tools
- [ ] **Global**: Búsqueda semántica < 500ms
- [ ] **Global**: Traversal de grafo < 100ms
- [ ] **Global**: Sistema no se cae por agregar memoria

---

## 🔗 Puntos de Integración Existentes (v0.0.57+)

1. **`src/context/builder.py`** — `build_system_prompt()`:
   - Punto de inyección para "## Relevant Past Memories" (FASE 3.5)

2. **`web/services/chat_stream.py:163`** — `background_tasks.add_task(_vectorize_session, ...)`:
   - Hook de vectorización automática al cerrar sesión ✅ funcionando

3. **`src/memory/vectorize_sessions.py`** — Pipeline completo:
   - Punto de integración para entity extraction (FASE 2)
   - Punto de integración para hash dedup (FASE 2.5)

4. **`src/tools/recall_memories.py`** — Búsqueda semántica:
   - Migrar a HybridRetriever cuando exista (FASE 3)

5. **`src/tools/manage_memory.py`** — Operaciones:
   - `clusters` y `topics` ✅ implementados
   - Futuro: `entities`, `graph`, `dedup`

6. **`src/memory/repos_memory/`** — Repositorios DI:
   - `MemoryRepositories` con `memory_index` + `vector_store` ✅
   - Futuro: `entity_repo` para entity graph

---

## Orden de Implementación Recomendado

```
Semana 1:  FASE 2  → Entity Graph (extracción + linking + tools)
Semana 2:  FASE 2.5 → Hash Dedup
           FASE 3  → Hybrid Retrieval (empieza)
Semana 3:  FASE 3  → Hybrid Retrieval (completa)
           FASE 3.5 → Inyección en System Prompt
Semana 4:  FASE 6  → Células de Memoria (curator nocturno)
           FASE 4  → Consolidación (poda + fusión)
Futuro:    FASE 5  → Proactividad
```

---

*Documento actualizado por Kairos para el proyecto K-Chat.*
*2026-06-16 — v0.0.57+ — Basado en investigación de Mem0 (58.7k⭐) y Letta (23.4k⭐)*
