# 🧠 K-Chat Memory Architecture — Roadmap

> Documento de planificación para el sistema de memoria multicapa de K-Chat.
> Creado: 2026-06-12 | Para compartir entre IAs del proyecto.

---

## 📐 Arquitectura General

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
│   │  │ ─── YA ES UN     │  │ ─ inline en SQL       │   │    │
│   │  │     GRAFO (FKs)  │  └──────────────────────┘   │    │
│   │  └──────────────────┘                            │    │
│   │  ┌──────────────────────────────────────────────┐│    │
│   │  │ Nuevo: Entity Graph                           ││    │
│   │  │ entities (nodos: persona, proyecto, tema...)  ││    │
│   │  │ relationships (aristas con FK + CASCADE)      ││    │
│   │  │ ─ CTE recursivo para traversal                ││    │
│   │  └──────────────────────────────────────────────┘│    │
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

### FASE 0 — Setup (hoy/mañana)

**Objetivo:** instalar dependencias y verificar que todo funcione

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

### FASE 1 — Memoria de Sesiones (esta semana)

**Objetivo:** guardar y recuperar memoria entre sesiones

```
[ ] Crear tabla `session_memories` en SQLite
    → id, session_id, summary TEXT, embedding BLOB, created_at
[ ] Session summarization al cerrar sesión
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
```

**Integración con el sistema actual:**
- Hook en `chat_stream.py` al finalizar el stream
- Hook en `build_system_prompt` (en `builder.py`)
- Nueva tool para el agente

---

### FASE 2 — Entity Graph (próxima semana)

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
| Grafo | **SQLite puro** (FK + cascade + CTE) | Maura ya usó este patrón, funciona, no necesita Neo4j |
| Framework memoria | **Custom** sobre SQLite | Control total, cero dependencias externas, se adapta a K-Chat |
| Session summary | **LLM al cierre** | El mismo modelo genera resúmenes, no requiere otro sistema |
| Retrieval trigger | **Al inicio + cuando el agente lo pida** | Híbrido: automático + bajo demanda |

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

### Puntos de inyección en el código existente:

1. **`src/context/builder.py`** → `build_system_prompt()`:
   - Aquí se inyectan las memorias recuperadas
   - Se agrega bloque `## Relevant Past Memories` al system prompt

2. **`web/services/chat_stream.py`** → `build_stream_generator()`:
   - Al finalizar el stream → disparar session summarization
   - En el `finally` block o después de `yield` final

3. **`src/tools/`** → Nuevas tools:
   - `recall_memories(query, limit)` → búsqueda semántica
   - `search_entities(query, type)` → búsqueda de entidades
   - `explore_graph(entity_id, depth)` → traversal

4. **`src/memory/repos/`** → Nuevos repositorios:
   - `MemoryRepository` → session_memories table
   - `EntityRepository` → entities + relationships
   - `VectorRepository` → sqlite-vec operations

---

## 🚀 Primer Paso Concreto

**Lo PRIMERO que hay que hacer:**

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

---

*Documento generado por Kairos (big-pickle) para el proyecto K-Chat.*
*2026-06-12 17:36*
