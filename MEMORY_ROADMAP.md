# 🧠 K-Chat Memory Architecture — Roadmap

> Documento de planificación para el sistema de memoria multicapa de K-Chat.
> Creado: 2026-06-12 | Actualizado: 2026-06-14 18:55

---

## 📐 Estado Actual (v0.0.56)

**Lo que YA existe y funciona:**

```
✅ MEMORY.md — archivo de texto plano, reescrito completo por save_memory
✅ save_memory tool — thread-safe, keys ordenadas alfabéticamente
✅ invalidate_context_cache() — se llama después de cada save_memory
✅ build_context_snapshot() — cache con Lock thread-safe, invalidation manual
✅ build_system_prompt() — lee SOUL.md + MEMORY.md + AGENTS.md + crash recovery
✅ MemoryIndexRepository — tabla memory_index con upsert/get/get_all/delete
✅ compressor.py — should_compress() + compress_history() con LLM
✅ history_rebuilder.py — rebuild desde SQLite
✅ 7 repositorios SQLite — Message, Session, ToolCall, SavedWidget, WidgetState, Debug, MemoryIndex
✅ Context cache con TTL (invalidation tras save_memory)
```

**Lo que NO existe todavía:**

```
❌ Embeddings (no hay modelo cargado, no hay vectores)
❌ Vector store (sqlite-vec no instalado)
❌ Entity graph (tablas entities/relationships no existen)
❌ Búsqueda semántica (no hay recall_memories)
❌ Session summarization automática (compressor existe pero no se usa al cierre)
❌ Hybrid retriever (no hay fusión vector+grafo)
❌ Proactividad (no hay "recuerdos pendientes")
```

---

## 📐 Arquitectura Objetivo

```
┌──────────────────────────────────────────────────────────────┐
│                     SYSTEM PROMPT                            │
│  (Soul.md + Memory.md + Agents.md + Tools.md + Memories)     │
└──────────────────────────┬───────────────────────────────────┘
                           │ inyección inteligente
                           ↓
┌──────────────────────────────────────────────────────────────┐
│                    RETRIEVAL LAYER                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Vector Search│  │ Graph Travers│  │ Token Budget     │   │
│  │ (semántico)  │  │ (relacional) │  │ + Reranking      │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘   │
└─────────┼──────────────────┼─────────────────────────────────┘
          │                  │
          ↓                  ↓
┌──────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                             │
│                                                              │
│   ┌────────────────────────────────────────────────────┐    │
│   │              SQLite (única DB)                      │    │
│   │                                                    │    │
│   │  ┌──────────────────┐  ┌──────────────────────┐   │    │
│   │  │ Tablas Actuales  │  │ Nueva: Vector Store   │   │    │
│   │  │ sessions         │  │ (sqlite-vec)          │   │    │
│   │  │ messages         │  │ ─ embeddings de cada  │   │    │
│   │  │ tool_calls       │  │   entidad/memoria     │   │    │
│   │  │ saved_widgets    │  │ ─ búsqueda semántica  │   │    │
│   │  │ widget_states    │  │ ─ inline en SQL       │   │    │
│   │  │ debug_info       │  └──────────────────────┘   │    │
│   │  │ memory_index     │                            │    │
│   │  │ widget_versions  │  ┌──────────────────────┐   │    │
│   │  │ ─── YA ES UN     │  │ Nuevo: Entity Graph   │   │    │
│   │  │     GRAFO (FKs)  │  │ entities (nodos)      │   │    │
│   │  └──────────────────┘  │ relationships (aristas)│   │    │
│   │                        │ ─ CTE recursivo        │   │    │
│   │                        └──────────────────────┘   │    │
│   └────────────────────────────────────────────────────┘    │
│                                                              │
│   Modelo de embeddings: sentence-transformers                │
│   └── all-MiniLM-L6-v2 (~80MB RAM, local)                   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🧩 Componentes del Sistema

### 1. Embedding Service (`src/memory/embeddings/`)
- Wrapper sobre sentence-transformers
- Carga el modelo una vez (singleton)
- Genera vectores de 384 dimensiones
- Cache de embeddings recientes
- Batch processing para eficiencia

### 2. Vector Store (`src/memory/vector/`)
- Wrapper sobre sqlite-vec
- Tabla virtual para vectores
- Insertar, buscar (KNN), actualizar, eliminar
- Metadata asociada a cada vector (tipo, entidad_id, timestamp)

### 3. Entity Graph (`src/memory/graph/`)
- Tablas: `entities`, `relationships`
- FK con ON DELETE CASCADE (patrón Mauro)
- CTE recursivo para queries de grafo
- Tipos de entidades: persona, proyecto, tool, widget, tema, sesión
- Tipos de relaciones: usa, crea, menciona, relacionado_a, depende_de

### 4. Session Summarizer (`src/memory/consolidation/`)
- Al cerrar sesión → resumen automático
- Extracción de entidades y relaciones
- Generación de embedding del resumen
- Almacenamiento en vector store + graph

### 5. Hybrid Retriever (`src/memory/retrieval/`)
- Toma el input actual → embedding → vector search
- Del resultado, extrae entidades → graph traversal
- Fusiona resultados, reranking, limita tokens
- Inyecta en system prompt

---

## 🗺️ Roadmap por Fases

### FASE 0 — Setup (✅ COMPLETADO parcialmente)

**Estado:** La infraestructura base existe. Falta solo la capa de vectores.

```
✅ src/memory/repos/ — 7 repositorios con base repository
✅ src/memory/repos/memory_index_repository.py — tabla memory_index funcional
✅ src/memory/schema.py — init_db_for_path() con migraciones
✅ src/memory/connection_pool.py — PooledConnection con WAL mode
✅ src/memory/bootstrap.py — ensure_db_initialized()
✅ src/memory/migration_runner.py — run_pending_migrations()
✅ src/memory/engine_state.py — DatabaseEngine Protocol
✅ src/memory/lifecycle.py — Thread-safe init tracking
✅ src/compressor.py — should_compress() + compress_history()
✅ src/context/runtime.py — ContextSnapshot con cache thread-safe
✅ src/context/builder.py — build_system_prompt() con crash recovery
```

**Pendiente para completar Fase 0:**
```
[ ] pip install sentence-transformers
[ ] Instalar sqlite-vec (.so o binario precompilado)
[ ] Verificar que la extensión se carga en SQLite
[ ] Crear src/memory/embeddings/service.py (carga del modelo)
[ ] Crear src/memory/vector/store.py (wrapper sqlite-vec)
[ ] Test: generar embedding, guardar en DB, buscar por similitud
```

**Archivos a crear:**
```
src/memory/embeddings/__init__.py
src/memory/embeddings/service.py
src/memory/vector/__init__.py
src/memory/vector/store.py
src/memory/vector/models.py
```

**Dependencias nuevas:** `sentence-transformers`, `sqlite-vec` (extensión C)

---

### FASE 1 — Memoria de Sesiones (⏳ PRÓXIMA)

**Objetivo:** guardar y recuperar memoria entre sesiones

**Puntos de integración identificados (v0.0.56):**

```
1. src/context/builder.py → build_system_prompt() Línea 63-91
   → Aquí se inyectan las memorias recuperadas
   → Se agrega bloque "## Relevant Past Memories" al system prompt
   → Ya tiene crash recovery block como patrón a seguir

2. web/services/chat_stream.py → build_stream_generator() Línea 56-187
   → En el finally block (L179-185) → disparar session summarization
   → Ya tiene save periódico (30s) y save final como patrón

3. src/tools/ → Nuevas tools con patrón DEFINITION + run()
   → recall_memories(query, limit) → búsqueda semántica
   → search_entities(query, type) → búsqueda de entidades
   → explore_graph(entity_id, depth) → traversal

4. src/memory/repos/ → Nuevos repositorios con patrón _BaseRepository
   → MemoryRepository → session_memories table
   → EntityRepository → entities + relationships
   → VectorRepository → sqlite-vec operations

5. src/memory/schema.py → Nuevas migraciones
   → migration_009_session_memories
   → migration_010_entities
   → migration_011_relationships
```

**Plan de implementación:**
```
[ ] Crear tabla `session_memories` en SQLite
    → id, session_id, summary TEXT, embedding BLOB, created_at
[ ] Session summarization al cerrar sesión
    → Hook en chat_stream.py finally block
    → LLM genera resumen de la conversación
    → Extrae temas principales, decisiones, entidades
[ ] Generar embedding del resumen
    → Guardar en sqlite-vec
[ ] Recuperación al iniciar nueva sesión
    → Embedding del primer mensaje del usuario
    → Vector search → top 5 sesiones similares
    → Inyectar resúmenes en system prompt
[ ] Tool: `recall_memories(query, limit=5)`
    → Búsqueda semántica de memorias pasadas
[ ] Tests: 7+ tests para MemoryRepository, embedding, retrieval
```

---

### FASE 2 — Entity Graph (semana 2)

**Objetivo:** estructura de conocimiento relacional

```
[ ] Crear tabla `entities`:
    → id UUID, type TEXT, name TEXT, metadata JSON, embedding BLOB
[ ] Crear tabla `relationships`:
    → source_id FK, target_id FK, relationship_type TEXT, weight REAL
    → ON DELETE CASCADE (patrón grafo)
[ ] Entity extraction al cerrar sesión
    → LLM extrae: personas, proyectos, tecnologías, temas
    → Crea/actualiza entities + relationships
[ ] Graph traversal con CTE recursivo
    → "dame todo lo conectado a X hasta profundidad 3"
[ ] Tool: `search_entities(query, type=None)`
    → Buscar entidades por nombre o similitud
[ ] Tool: `explore_graph(entity_id, depth=2)`
    → Explorar relaciones de una entidad
[ ] Tests: 7+ tests para EntityRepository, graph traversal
```

**Ejemplo de consulta:**
```sql
-- Encontrar todo lo conectado a un proyecto
WITH RECURSIVE chain AS (
    SELECT source_id, target_id, 1 AS depth
    FROM relationships WHERE source_id = 'proyecto-kairos'
    UNION ALL
    SELECT r.source_id, r.target_id, c.depth + 1
    FROM relationships r JOIN chain c ON r.source_id = c.target_id
    WHERE c.depth < 3
)
SELECT e.name, e.type FROM chain c
JOIN entities e ON e.id = c.target_id;
```

---

### FASE 3 — Retrieval Híbrido (semana 3)

**Objetivo:** combinar vectores + grafo para contexto óptimo

```
[ ] HybridRetriever class:
    → Input → vector search → top K memorias
    → De esas memorias → extraer entidades → graph traversal
    → Fusionar resultados con pesos
    → Reranking por relevancia + temporal
[ ] Token budget management
    → Calcular tokens disponibles en context window
    → Priorizar memorias por score
    → Truncar si excede límite
[ ] Cache de memorias "calientes"
    → Memorias accedidas frecuentemente se mantienen en RAM
[ ] Inyección en system prompt
    → Bloque "## Relevant Past Memories" auto-generado
    → Solo aparece si hay memorias relevantes
[ ] Tests: integration tests del retriever completo
```

**Arquitectura del retriever:**
```
User Input
    ↓
[Vector Search] ← sqlite-vec
    ↓ (top 10 memorias)
[Entity Extraction] ← NER del texto
    ↓
[Graph Traversal] ← CTE recursivo
    ↓
[Fusion + Reranking]
    ↓
[Token Budget Check]
    ↓
[Inject into system prompt]
```

---

### FASE 4 — Consolidación y Mantenimiento (ongoing)

**Objetivo:** que la memoria no se llene de basura

```
[ ] Consolidación periódica:
    → Fusionar memorias similares (similitud > 0.9)
    → Actualizar embeddings de entidades fusionadas
[ ] Compaction:
    → Resumir bloques viejos en meta-resúmenes semanales
    → Eliminar versiones antiguas de entidades actualizadas
[ ] Decay:
    → Bajar weight de relaciones no accedidas en >30 días
    → Eliminar relaciones con weight < umbral
[ ] Self-reflection:
    → El agente escribe notas sobre su propio rendimiento
    → "esto que hice funcionó bien", "esto no funcionó"
    → Se guarda como memoria procedural
[ ] Background scheduler:
    → Consolidación diaria (idle)
    → Compaction semanal
    → Decay mensual
```

---

### FASE 5 — Proactividad (visión)

**Objetivo:** que el agente recuerde cosas sin preguntar

```
[ ] Sistema de "recuerdos pendientes"
    → Mauro: "acordame de X mañana"
    → Se guarda con timestamp + condición
    → Se revisa al iniciar cada sesión
[ ] Detección de patrones
    → "Siempre preguntás sobre Y los fines de semana"
    → El sistema lo aprende y lo sugiere
[ ] Modo proactivo
    → "La última vez que hablamos de esto, dijiste que..."
    → Sin esperar a que Mauro pregunte

Esto es FUTURO. Primero hay que tener las bases sólidas.
```

---

## 📦 Decisiones Técnicas

| Decisión | Opción elegida | Por qué |
|----------|---------------|---------|
| Vector DB | **sqlite-vec** | Misma DB que ya usamos, 0 servers extra, suficiente para miles de vectores |
| Embeddings | **all-MiniLM-L6-v2** | ~80MB RAM, corre local, calidad decente, sin API keys |
| Grafo | **SQLite puro** (FK + cascade + CTE) | Mauro ya usó este patrón, funciona, no necesita Neo4j |
| Framework memoria | **Custom** sobre SQLite | Control total, cero dependencias externas, se adapta a K-Chat |
| Session summary | **LLM al cierre** | El mismo modelo genera resúmenes, no requiere otro sistema |
| Retrieval trigger | **Al inicio + cuando el agente lo pida** | Híbrido: automático + bajo demanda |
| DI pattern | **Repository pattern** con _BaseRepository | Ya establecido en los 7 repos actuales |
| Tool pattern | **DEFINITION + run()** con auto-discovery | Ya establecido en las 20+ tools actuales |
| Migration pattern | **Sequential** con schema_version table | Ya establecido en 8 migraciones |

---

## 📊 Métricas de Éxito

- [ ] El asistente recuerda información entre sesiones
- [ ] Puede responder "¿de qué hablamos sobre X?" con precisión
- [ ] Las memorias no ocupan más del 30% del context window
- [ ] El sistema no se cae por agregar memoria
- [ ] La búsqueda semántica toma < 500ms
- [ ] El grafo tiene < 100ms de traversal

---

## 🔗 Integración con el Sistema Actual

### Puntos de inyección en el código existente (v0.0.56):

1. **`src/context/builder.py:63-91`** → `build_system_prompt()`:
   - Aquí se inyectan las memorias recuperadas
   - Se agrega bloque `## Relevant Past Memories` al system prompt
   - Ya tiene crash recovery block como patrón (L68-71)

2. **`web/services/chat_stream.py:179-185`** → `finally` block:
   - Al finalizar el stream → disparar session summarization
   - Ya tiene save periódico (30s) y save final como patrón

3. **`src/tools/`** → Nuevas tools con patrón DEFINITION + run():
   - `recall_memories(query, limit)` → búsqueda semántica
   - `search_entities(query, type)` → búsqueda de entidades
   - `explore_graph(entity_id, depth)` → traversal

4. **`src/memory/repos/`** → Nuevos repositorios con patrón _BaseRepository:
   - `MemoryRepository` → session_memories table
   - `EntityRepository` → entities + relationships
   - `VectorRepository` → sqlite-vec operations

5. **`src/memory/schema.py`** → Nuevas migraciones:
   - `migration_009_session_memories`
   - `migration_010_entities`
   - `migration_011_relationships`

---

## 🚀 Primer Paso Concreto

**Lo PRIMERO que hay que hacer (FASE 0 pendiente):**

```
1. pip install sentence-transformers
2. Descargar sqlite-vec (.so)
3. Crear archivo: src/memory/embeddings/service.py
   → Cargar modelo all-MiniLM-L6-v2
   → Función: generate_embedding(texto) → vector
4. Crear archivo: src/memory/vector/store.py
   → Inicializar tabla virtual vec0
   → Función: insert_vector(id, embedding, metadata)
   → Función: search_similar(embedding, k) → results
5. Test: embedding → guardar → buscar → verificar
```

Eso es **TODO** el paso 1. Una vez que eso funcione, el resto es agregar lógica arriba.

**Prerequisito antes de FASE 0:**
```
[ ] Verificar que sentence-transformers cabe en 4GB RAM (el modelo son ~80MB)
[ ] Verificar compatibilidad de sqlite-vec con Python 3.14
[ ] Decidir: ¿instalar sentence-transformers o usar una API de embeddings?
    → Si RAM es problema, usar API (pero agrega dependencia externa)
```

---

*Documento actualizado por Kairos (mimo-v2.5) para el proyecto K-Chat.*
*2026-06-14 18:55 — v0.0.56*
