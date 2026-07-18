# 🧠 K-Chat Memory Architecture — Complete Reference

> **Versión:** 1.0 — Junio 2026
> **Propósito:** Fuente de verdad única sobre el sistema de memoria de K-Chat. Arquitectura, flujos, herramientas, bugs críticos y roadmap.

---

## 1. Overview

### Timeline

K-Chat pasó de **cero a estado actual en 10 días** (6–16 de junio de 2026). El sistema de memoria fue el último gran subsistema en consolidarse, pero hoy es el más complejo.

### Stack de memoria

| Capa | Tecnología | Propósito |
|---|---|---|
| MEMORY.md | Archivo de texto (Markdown) | Fuente de verdad legible, control de versiones |
| memory.db | SQLite (global syncable) | Memoria estructurada, entidades, grafos |
| sessions.db | SQLite (local por dispositivo) | Mensajes, vectores, clusters |

### Métricas clave

| Métrica | Valor |
|---|---|
| Clusters temáticos | ~160 |
| Entidades conocidas | ~48 |
| Relaciones entre entidades | ~20 |
| Tools de memoria | 10+ |
| Procesos de background | 6+ |

### Principios de diseño

- **Dual-write**: Cada dato vive en MEMORY.md (texto) y memory.db (estructurado). Eventualmente consistente.
- **Inyección por presupuesto**: No se inyecta todo — se prioriza por relevancia bajo un token budget.
- **3 señales de retrieval**: Vector (semántico) + Keyword (léxico) + Entity (gráfo). Fusión RRF.
- **Background todo**: Vectorización, clustering, curación — todo corre post-stream, nunca bloquea al usuario.

---

## 2. Three Database Layers

### 2.1 MEMORY.md

**Path:** `~/dev/K-Chat/MEMORY.md`

**Formato:** Markdown con secciones semánticas parseables por `read_memory_section()`.

Es la **fuente de texto** del sistema. Se escribe en paralelo con memory.db (dual-write no transaccional — ver bug #11).

**Secciones usadas:**
- `## Temas` / `## Topics` — clusters temáticos
- `## Entidades` / `## Entities` — entidades conocidas
- `## Preferences` / `## Preferencias` — preferencias del usuario
- `## Projects` / `## Proyectos` — proyectos activos
- `## Stack` — stack tecnológico

---

### 2.2 memory.db (Global syncable)

**Path:** `~/dev/K-Chat/memory.db` (configurable via `MEMORY_DB_PATH`)

**Tablas:**

```sql
-- Entidades del grafo
CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    entity_type TEXT DEFAULT 'unknown',
    description TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Relaciones del grafo
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES entities(id),
    target_id INTEGER NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices del grafo
CREATE INDEX idx_relations_source ON relations(source_id);
CREATE INDEX idx_relations_target ON relations(target_id);
CREATE INDEX idx_relations_type ON relations(relation_type);
CREATE INDEX idx_entities_name ON entities(name);
CREATE INDEX idx_entities_type ON entities(entity_type);

-- Memoria estructurada (sync con MEMORY.md)
CREATE TABLE memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    importance INTEGER DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_memory_key ON memory(key);
CREATE INDEX idx_memory_category ON memory(category);

-- Memoria cronológica (append-only log)
CREATE TABLE memory_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    action TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 2.3 sessions.db (Local per-device)

**Path:** Resuelto por `get_db_path()`:
1. `SESSIONS_DB_PATH` env var
2. `~/.kchat/sessions.db`
3. `./sessions.db`

**Tablas:**

```sql
-- Sesiones de chat
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    model TEXT,
    system_prompt TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

-- Mensajes individuales
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    model TEXT,
    tokens INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- Vectores de embeddings
CREATE TABLE message_vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    vector BLOB NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_message_vectors_message ON message_vectors(message_id);
CREATE INDEX idx_message_vectors_session ON message_vectors(session_id);

-- Clusters temáticos
CREATE TABLE clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    centroid BLOB,
    keywords TEXT DEFAULT '[]',
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cluster_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    distance REAL,
    UNIQUE(cluster_id, message_id)
);

CREATE INDEX idx_cluster_members_cluster ON cluster_members(cluster_id);

-- Sesiones eliminadas (isla — ver bug #10)
CREATE TABLE deleted_sessions (
    id TEXT PRIMARY KEY,
    session_data TEXT,
    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Complete Data Flow Diagrams

### 3.1 Write Flow

```
save_memory(key, value)
    │
    ├──▶ MEMORY.md append/update (texto)
    │
    ├──▶ memory.db INSERT/UPDATE (estructurado)
    │
    ├──▶ Cache invalidation (incluso si falla — bug #4)
    │
    └──▶ Vector store (si aplica)
            │
            └──▶ Embedding generation
                    │
                    └──▶ ANN index update
```

### 3.2 Read Flow

```
build_system_prompt(session_context)
    │
    ├──▶ Auto-retrieval trigger (si aplica)
    │       │
    │       ├──▶ HybridRetriever.retrieve(query)
    │       │       │
    │       │       ├──▶ VectorRetriever (ANN)
    │       │       ├──▶ KeywordRetriever (FTS5/BFS)
    │       │       └──▶ EntityRetriever (grafo CTE)
    │       │
    │       └──▶ RRF fusion → Cross-encoder rerank
    │               │
    │               └──▶ Token budget truncation
    │
    └──▶ Context injection into system prompt
            │
            └──▶ MEMORY.md section reads
                    │
                    └──▶ memory.db structured reads
```

### 3.3 Recibos de memoria e hidratación bajo demanda

Cada resultado recuperado en el turno actual se inyecta completo y queda asociado a
un recibo estable (`mr_<hash>`). En turnos posteriores, el prompt conserva solamente
un ledger compacto con ID, etiqueta, extracto y consulta disparadora. Si el tema vuelve
a ser relevante, `hydrate_memory_receipt` resuelve el recibo dentro de la sesión actual
y carga la memoria canónica o el intercambio original junto con una ventana de contexto.

La identidad lógica es `(session_id, source, source_key, item_idx)`: una nueva versión
del mismo recuerdo actualiza el recibo existente con el último vector y `content_hash`,
sin duplicar versiones calientes en el contexto. Los embeddings históricos continúan
en `memory.db`; el recibo es un puntero consultable, no otra copia del contenido.

### 3.4 Session Vectorization Flow

```
chat_stream → complete → background_tasks
    │
    └──▶ vectorize_sessions()
            │
            ├──▶ Fetch unvectorized exchanges (NOT vectorized)
            │
            ├──▶ Keyword extraction (TF-IDF style)
            │
            ├──▶ Noise filter (stop-words + short tokens)
            │
            ├──▶ Hash dedup (primeros 4000 chars — bug #6)
            │
            ├──▶ Entity extraction (lexicon + regex)
            │
            ├──▶ Embedding generation (sync call — bug #9)
            │
            ├──▶ Store:
            │       ├──▶ message_vectors (SQLite BLOB)
            │       ├──▶ entities (si nuevas)
            │       └──▶ relations (si conecta)
            │
            └──▶ Cluster assignment (k-means online)
```

### 3.4 Curation Flow (MANUAL — Gardener)

```
│   Script: python -m src.scripts.curate
│   No hay timer — se ejecuta manualmente
│
├──▶ Gardener (gardener.py)
│       │
│       ├──▶ Lee MEMORY.md completo
│       ├──▶ Lee memory.db completo
│       ├──▶ Detecta inconsistencias (dual-write drift)
│       ├──▶ Identifica stale entries
│       ├──▶ Sugiere consolidaciones
│       │
│       └──▶ Output: consolidated_memory.md
│
├──▶ Tracer (tracer.py)
│       │
│       ├──▶ Lee conversaciones (sessions.db)
│       ├──▶ Extrae patrones de interacción
│       ├──▶ Identifica temas recurrentes
│       ├──▶ Detecta cambios de humor/metas
│       │
│       └──▶ Output: trace_report.md
│
└──▶ Curator LLM (curate.py)
        │
        ├──▶ Toma inputs de Gardener + Tracer
        ├──▶ Extrae entidades, relaciones, clusters
        ├──▶ Escribe a MEMORY.md
        ├──▶ Escribe a memory.db
        │
        └──▶ Checkpoint: tmp/curator_checkpoint.json
                │
                └──▶ Bug #5: timestamp con formato
                        %Y-%Y-%m-%d en vez de %Y-%m-%d
```

### 3.5 Hybrid Retrieval Flow

```
retrieve(query, top_k=5)
    │
    ├─── Signal 1: VectorRetriever ──────▶ similarity_search(query, k=20)
    │       score = cosine_similarity(query_embedding, doc_embedding)
    │
    ├─── Signal 2: KeywordRetriever ─────▶ keyword_search(query, k=20)
    │       score = BM25 / token overlap
    │       bug: source_filter se ignora
    │
    ├─── Signal 3: EntityRetriever ──────▶ entity_search(query, k=20)
    │       score = entity mention count + relation weight
    │       bug: source_filter se ignora
    │       bug: case-sensitive (bug #2)
    │
    ├─── RRF Fusion ──────────────────────▶ fusion.py
    │       score = Σ 1/(rank + k)
    │       bug: min_score=0.15 filtra todo (bug #1)
    │
    ├─── Cross-encoder Rerank ───────────▶ rerank(query, candidates)
    │       (M model de reranking)
    │
    └─── Token Budget ────────────────────▶ truncate_to_budget(context, max_tokens)
            │
            └───▶ Smart injection:
                    ├─── 0. High priority (matches entities in query)
                    ├─── 1. Recent (timestamp filter)
                    └─── 2. Budget remainder
```

---

## 4. Tool Reference

### 4.1 `save_memory`

**Propósito:** Guardar un par key/value en ambos sistemas (MEMORY.md + memory.db).

| Parámetro | Tipo | Descripción |
|---|---|---|
| `key` | string | Identificador único (ej. `user:prefs:theme`) |
| `value` | string | Contenido a guardar |
| `category` | string? | Categoría opcional (`general` por defecto) |
| `importance` | int? | 1-10 (5 por defecto) |

**Side effects:**
- Invalida cache de `build_system_prompt` **incluso si la escritura falla** (bug #4)
- Dispara dual-write no atómico (bug #11)

---

### 4.2 `recall_memories`

**Propósito:** Obtener memorias por key prefix.

| Parámetro | Tipo | Descripción |
|---|---|---|
| `prefix` | string | Prefix de key a buscar |
| `limit` | int? | Máximo resultados (10 por defecto) |

---

### 4.3 `memory_search`

**Propósito:** Búsqueda semántica por embedding de memoria.

| Parámetro | Tipo | Descripción |
|---|---|---|
| `query` | string | Texto a buscar |
| `k` | int? | Resultados (5 por defecto) |

---

### 4.4 `list_memories`

**Propósito:** Listar todas las keys de memoria.

| Parámetro | Tipo | Descripción |
|---|---|---|
| `category` | string? | Filtrar por categoría |

---

### 4.5 `manage_memory`

**Propósito:** Operaciones CRUD sobre el sistema de memoria.

**11 sub-operaciones:**

| Operación | Descripción |
|---|---|
| `cleanup` | Elimina entradas stale o huérfanas |
| `consolidate` | Fusiona entradas duplicadas |
| `sync_from_file` | Lee MEMORY.md y escribe a memory.db |
| `sync_to_file` | Lee memory.db y escribe a MEMORY.md |
| `search` | Búsqueda textual en memorias |
| `delete` | Elimina entrada por key |
| `update` | Actualiza valor de entrada existente |
| `history` | Muestra historial de cambios |
| `export` | Exporta memorias a JSON |
| `import` | Importa memorias desde JSON |
| `stats` | Estadísticas del sistema |

---

### 4.6 `search_entities`

**Propósito:** Búsqueda de entidades por nombre o tipo.

| Parámetro | Tipo | Descripción |
|---|---|---|
| `name` | string? | Nombre exacto o parcial |
| `entity_type` | string? | Filtrar por tipo |
| `limit` | int? | 10 por defecto |

---

### 4.7 `explore_graph`

**Propósito:** Traversar el grafo de entidades desde un nodo.

| Parámetro | Tipo | Descripción |
|---|---|---|
| `entity_name` | string | Nodo de inicio |
| `depth` | int? | Profundidad de traversal (2 por defecto) |

**Bug crítico:** Solo traversa source→target, no target→source (bug #8).

---

## 5. Background Processes

### 5.1 Curator (Gardener + Tracer + LLM)

| Aspecto | Detalle |
|---|---|
| **Trigger** | Manual (`python -m src.scripts.curate`) |
| **Timer** | ❌ No instalado |
| **Componentes** | `gardener.py`, `tracer.py`, `curate.py` |
| **Pipeline** | Gardener consolida → Tracer extrae → Curator LLM escribe |
| **Checkpoint** | `tmp/curator_checkpoint.json` |
| **Bug** | Formato fecha: `%Y-%Y-%m-%d` (bug #5) |

### 5.2 Session Vectorization

| Aspecto | Detalle |
|---|---|
| **Trigger** | `background_tasks.add_task(vectorize_sessions)` post-stream |
| **Archivo** | `src/scripts/vectorize_sessions.py` |
| **Pipeline** | Fetch → Keywords → Noise filter → Hash dedup → Entities → Embedding → Store → Cluster |
| **Hash dedup** | Solo primeros 4000 chars (bug #6) |
| **Embedding** | Llamada sincrónica (bug #9) |
| **Entity extraction** | Inline, lexicon + regex (~50 entities) |

### 5.3 Hash Dedup

**Ubicación:** `vectorize_sessions.py:172`

**Funcionamiento:**
- Calcula hash MD5 del contenido del mensaje
- Si el hash ya existe en `message_vectors`, saltea
- Usa solo primeros 4000 caracteres del contenido

**Bug:** Si dos mensajes difieren solo después del char 4000, uno se pierde.

### 5.4 Entity Extraction (inline)

**Ubicación:** Inline en `vectorize_exchange()` dentro de `vectorize_sessions.py`

**Mecanismo:**
- Lexicon-based: matchea nombres de ~50 entidades conocidas
- Regex patterns: emails, URLs, fechas, IDs de proyecto
- Post-linkeo: conecta con entidades existentes en grafo

---

## 6. Entity Graph

### 6.1 Extractor

| Aspecto | Detalle |
|---|---|
| **Método** | Lexicon-based + regex patterns |
| **Entidades conocidas** | ~50 |
| **Fuente** | Extraídas de conversaciones + curator |
| **Output** | Tuplas (entity_name, entity_type, context) |

### 6.2 Linker

| Aspecto | Detalle |
|---|---|
| **Mecanismo** | In-memory con flush periódico |
| **Criterio** | Co-ocurrencia en misma conversación + umbral de peso |
| **Persistencia** | `relations` table en memory.db |

### 6.3 Graph Traversal

| Aspecto | Detalle |
|---|---|
| **Mecanismo** | CTE recursivo en SQLite |
| **Archivo** | `entity_repo.py:explore_graph()` |
| **Dirección** | Solo source→target (bug #8) |
| **Profundidad** | Configurable (default 2) |

### 6.4 Limitaciones Conocidas

1. **Case-sensitivity** (bug #2): `entity_search` hace matching case-sensitive. Buscar "python" no encuentra "Python".
2. **Unidireccional** (bug #8): `explore_graph` solo recorre source→target. Las relaciones target→source no aparecen.
3. **Sin weight decay**: El peso de las relaciones no decae con el tiempo.

---

## 7. Critical Bugs

### Bug #1 — RRF min_score=0.15 kills all hybrid results

| Campo | Detalle |
|---|---|
| **Archivo** | `fusion.py:104` |
| **Síntoma** | Hybrid retrieval siempre devuelve 0 resultados |
| **Causa** | `min_score=0.15` filtra scores RRF que típicamente son ~0.01-0.05 |
| **Impacto** | ❌ CRÍTICO — Todo hybrid retrieval roto |
| **Fix** | Bajar umbral a `min_score=0.001` o eliminarlo |

### Bug #2 — entity_search case-sensitive

| Campo | Detalle |
|---|---|
| **Archivo** | `entity_search.py:43-44` |
| **Síntoma** | `entity_search("Mauro")` encuentra, `entity_search("mauro")` no |
| **Causa** | `WHERE name = ?` en vez de `WHERE LOWER(name) = LOWER(?)` |
| **Impacto** | ❌ CRÍTICO — Entity retrieval incoherente |
| **Fix** | Usar `LOWER()` en ambos lados del WHERE |

### Bug #3 — VectorStore `_init_tables()` missing `relevance_score` column

| Campo | Detalle |
|---|---|
| **Archivo** | `vector/store.py:76-87` |
| **Síntoma** | Reranking falla porque no existe columna `relevance_score` |
| **Causa** | Schema mismatch entre código de reranking y schema real |
| **Impacto** | ❌ CRÍTICO — Cross-encoder reranking no funciona |
| **Fix** | Agregar columna o adaptar query |

### Bug #4 — save_memory invalida cache incluso en write failure

| Campo | Detalle |
|---|---|
| **Archivo** | `save_memory.py:152-153` |
| **Síntoma** | Si falla la escritura (disk full, etc.), la cache se invalida igual |
| **Causa** | Cache invalidation antes de verificar éxito |
| **Impacto** | ⚠️ ALTO — Pérdida de cache útil |
| **Fix** | Mover cache invalidation después del write exitoso |

### Bug #5 — Curator checkpoint timestamp `%Y-%Y-%m-%d`

| Campo | Detalle |
|---|---|
| **Archivo** | `curate.py:307` |
| **Síntoma** | Checkpoint timestamp sale como `2026-2026-06-15` |
| **Causa** | Typo: `%Y-%Y-%m-%d` en vez de `%Y-%m-%d` |
| **Impacto** | 🟡 MEDIO — Checkpoint datetime no parseable |
| **Fix** | Corregir format string |

### Bug #6 — Hash dedup solo usa primeros 4000 chars

| Campo | Detalle |
|---|---|
| **Archivo** | `vectorize_sessions.py:172` |
| **Síntoma** | Dos mensajes que difieren en último 1% se consideran duplicados |
| **Causa** | `content[:4000]` sin hash de contenido completo |
| **Impacto** | 🟡 MEDIO — Pérdida de mensajes casi duplicados |
| **Fix** | Usar hash del contenido completo, no truncado |

### Bug #7 — keyword_search & entity_search ignoran `source_filter`

| Campo | Detalle |
|---|---|
| **Archivo** | `hybrid_retriever.py:95-98` |
| **Síntoma** | `source_filter="memory"` no excluye vectores ni viceversa |
| **Causa** | Parámetro recibido pero no aplicado en las queries internas |
| **Impacto** | 🟡 MEDIO — Filtros de fuente no funcionales |
| **Fix** | Propagar `source_filter` a las queries SQL/FTS5 |

### Bug #8 — EntityRepository.explore_graph() solo traversa source→target

| Campo | Detalle |
|---|---|
| **Archivo** | `entity_repo.py:168-176` |
| **Síntoma** | `explore_graph("Python")` no muestra qué entidades apuntan a Python |
| **Causa** | CTE recursivo solo sigue `source_id → target_id` |
| **Impacto** | 🟡 MEDIO — Grafo invisible en una dirección |
| **Fix** | UNION con traversal inverso en la CTE |

### Bug #9 — session_repository.py llama generate_embedding() sync

| Campo | Detalle |
|---|---|
| **Archivo** | `session_repository.py:153` |
| **Síntoma** | Vectorización de sesión bloquea el event loop |
| **Causa** | `generate_embedding()` es async pero se llama con `await` en contexto sync |
| **Impacto** | 🟡 MEDIO — Performance, no correctness |
| **Fix** | Hacer el caller async o usar `asyncio.run()` |

### Bug #10 — Deleted sessions DB es una isla

| Campo | Detalle |
|---|---|
| **Archivo** | Schema en `sessions.db` — tabla `deleted_sessions` |
| **Síntoma** | La tabla existe pero nunca se escribe ni se lee |
| **Causa** | Código de delete nunca implementó el volcado a esta tabla |
| **Impacto** | 🟢 BAJO — Dead code, cero impacto funcional |
| **Fix** | Eliminar tabla o implementar el volcado |

### Bug #11 — Dual-write not atomic (MEMORY.md ↔ memory.db)

| Campo | Detalle |
|---|---|
| **Archivo** | `save_memory.py` (todo el módulo) |
| **Síntoma** | MEMORY.md y memory.db pueden divergir si el proceso crashea a mitad |
| **Causa** | No hay transacción entre archivo de texto y SQLite |
| **Impacto** | ⚠️ ALTO — Estado inconsistente eventual |
| **Fix** | Implementar write-ahead log o transacción de dos fases |

### Bug #12 — Connection pools thread-safety issues

| Campo | Detalle |
|---|---|
| **Archivo** | Múltiples repositorios que usan SQLite |
| **Síntoma** | `SQLite objects created in a thread can only be used in that same thread` |
| **Causa** | SQLite no es thread-safe por defecto; conexiones compartidas entre hilos |
| **Impacto** | 🟡 MEDIO — Race conditions intermitentes |
| **Fix** | Usar `check_same_thread=False` + pool local por hilo |

---

## 8. Roadmap Status — Real vs Documentado

| Fase | Descripción | Roadmap dice | Realidad | Estado |
|---|---|---|---|---|
| FASE 0 | Embeddings | ✅ | ✅ Completado | ✅ |
| FASE 7 | Clustering | ✅ | ✅ Completado | ✅ |
| FASE 2 | Entity Graph | PRÓXIMA | ✅ IMPLEMENTADO | ✅ |
| FASE 2.5 | Hash Dedup | PRÓXIMA | ✅ IMPLEMENTADO | ✅ |
| FASE 3 | Hybrid Retrieval | PRÓXIMA | ✅ IMPLEMENTADO | ✅ (roto por bug #1) |
| FASE 3.5 | Smart Injection | PRÓXIMA | ✅ IMPLEMENTADO | ✅ |
| FASE 4 | Consolidation | ✅ (Gardener) | ✅ Completado | ✅ |
| FASE 6 | Curator Cells | PRÓXIMA | ✅ IMPLEMENTADO | ✅ |
| FASE 5 | Proactivity | ❌ | ❌ No empezado | ❌ |

**Nota:** La documentación del roadmap (MEMORY.md u otros archivos) marca FASE 2, 2.5, 3, 3.5 y 6 como "PRÓXIMA", pero **ya están implementadas**. Esto es un desfase documentación vs realidad. FASE 5 (Proactivity) es la única genuinamente no empezada.

---

## 9. Quick Reference

### 9.1 File Paths

| Archivo | Propósito |
|---|---|
| `MEMORY.md` | Fuente de verdad texto |
| `src/memory/save_memory.py` | Tool save_memory |
| `src/memory/recall_memories.py` | Tool recall_memories |
| `src/memory/memory_search.py` | Tool memory_search |
| `src/memory/manage_memory.py` | Tool manage_memory (11 ops) |
| `src/memory/search_entities.py` | Tool search_entities |
| `src/memory/explore_graph.py` | Tool explore_graph |
| `src/memory/entity_repo.py` | EntityRepository, grafo CTE |
| `src/memory/fusion.py` | RRF fusion + reranking |
| `src/retrieval/hybrid_retriever.py` | HybridRetriever (3 señales) |
| `src/retrieval/vector_retriever.py` | ANN vector retrieval |
| `src/retrieval/keyword_retriever.py` | Keyword/FTS5 retrieval |
| `src/retrieval/entity_retriever.py` | Entity graph retrieval |
| `src/retrieval/entity_search.py` | Entity search query builder |
| `src/vector/store.py` | VectorStore, init/schema |
| `src/scripts/vectorize_sessions.py` | Background vectorization |
| `src/scripts/curate.py` | Curator LLM orchestration |
| `src/scripts/gardener.py` | Consolidation gardener |
| `src/scripts/tracer.py` | Pattern tracer |
| `src/repository/session_repository.py` | Session DB access |
| `src/db.py` | DB path resolution, connection pool |
| `~/.config/opencode/AGENTS.md` | Global agent rules |
| `AGENTS.md` (project root) | K-Chat project agent rules |

### 9.2 Environment Variables

| Variable | Default | Descripción |
|---|---|---|
| `MEMORY_DB_PATH` | `~/dev/K-Chat/memory.db` | Ruta a memory.db |
| `SESSIONS_DB_PATH` | `~/.kchat/sessions.db` | Ruta a sessions.db |
| `OPENAI_API_KEY` | — | API key para LLM |
| `OPENAI_MODEL` | `gpt-4o` | Modelo por defecto |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Modelo de embeddings |
| `EMBEDDING_DIMENSIONS` | `1536` | Dimensiones del vector |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `VECTOR_STORE_PATH` | `~/.kchat/vectors/` | Ruta a índices ANN |

### 9.3 Tools

| Tool | Descripción |
|---|---|
| `save_memory` | Guarda key/value en MEMORY.md + memory.db |
| `recall_memories` | Busca por key prefix |
| `memory_search` | Búsqueda semántica |
| `list_memories` | Lista todas las keys |
| `manage_memory` | CRUD completo (11 sub-ops) |
| `search_entities` | Busca entidades por nombre/tipo |
| `explore_graph` | Traversa grafo desde entidad |
| `web_search` | Búsqueda en web |
| `fetch_url` | Obtiene contenido de URL |
| `read_file` | Lee archivos |
| `search_files` | Busca texto en archivos |

---

> **Mantenimiento:** Este documento debe actualizarse cada vez que se modifique el sistema de memoria. Si agregás un tool, un flujo, o corregís un bug, actualizá la sección correspondiente.
