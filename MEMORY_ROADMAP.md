# MEMORY_ROADMAP.md — Estado real, problemas detectados y plan de acción

> **Fecha de investigación:** 2026-06-29  
> **Basado en:** lectura directa de `src/memory/`, `src/coordination/`, MEMORY_ARCHITECTURE.md, ROADMAP_DISTRIBUTED_KAIROS.md, y git history.  
> **Propósito:**DOCUMENTar lo que el sistema de memoria TIENE, lo que le FALTA, y los problemas reales detectados al trazar el flujo completo. No especulativo — cada afirmación verificada contra código.

---

## 1. Lo que el sistema YA TIENE (y Mauro no recordaba que tenía)

Mauro pensó que el sistema "ya debería tener cosas para evitar eso (dedup, embeddings)". Verifiqué: **SÍ las tiene**. El problema no es que no existan — es que están incompletas o mal cableadas para el escenario multi-nodo.

### 1.1 Dedup por content_hash — ✅ IMPLEMENTADO

El sistema YA tiene deduplicación por content_hash en **dos capas**:

**Capa 1 — VectorStore** (`src/memory/vector/store.py`):
```python
# vec_meta tiene columnas:
#   hash TEXT DEFAULT ''
#   content_hash TEXT  ← indexado con idx_vec_meta_content_hash
```
- `find_by_hash(hash, source)` consulta por `hash` (MD5 del texto normalizado)
- `insert(..., hash=..., content_hash=...)` guarda ambos hashes
- Índice `idx_vec_meta_content_hash` para búsqueda rápida

**Capa 2 — memory_work_catalog** (`src/memory/repos_memory/work_catalog_repo.py`):
Tabla `memory_work_catalog` con:
```sql
PRIMARY KEY (source, source_key, item_idx)
-- status: 'pending' | 'embedded' | 'deduped' | 'noise'
-- content_hash TEXT (indexado)
-- vec_rowid INTEGER (link al vector)
```
- `is_processed()` verifica si un item ya fue procesado
- `mark()` registra el resultado (embedded / deduped / noise)
- `max_processed_idx()` permite vectorización incremental (resume desde el último idx)

**Capa 3 — vectorize_sessions.py** (`src/memory/vectorize_sessions.py`):
El pipeline de vectorización YA consulta dedup antes de embeder:
```python
# Línea 437-467: Check contra DB first (persistent dedup via content_hash)
existing = store._get_conn().execute(
    "SELECT rowid FROM vec_meta WHERE content_hash = ?", (text_hash,)
).fetchone()
if existing is not None:
    _catalog_mark(catalog, session_id, idx, text_hash, "deduped", ...)
    continue  # ← NO recalcula el embedding
```

**Conclusión:** el sistema NO recalcula embeddings duplicados *dentro del mismo nodo*. El problema es **cross-nodo**: cada nodo tiene su propia `memory.db` con su propio `vec_meta` y `memory_work_catalog`. Un texto vectorizado en la laptop NO es visto por la PC grande viceversa.

### 1.2 Node identity y platform detection — ✅ IMPLEMENTADO (con limitaciones)

`src/coordination/node_state.py`:
```python
# _default_node_id(): Usa socket.gethostname() como node_id
# _platform: Usa config.node_platform o platform.system().strip().lower()
#           → "linux" o "windows"
```

`src/config_loader.py`:
```python
node_id: str = os.getenv("KAIROS_NODE_ID", "")      # override manual
node_role: str = os.getenv("KAIROS_NODE_ROLE", "secondary")
node_platform: str = os.getenv("KAIROS_NODE_PLATFORM", "")  # override manual
```

**El sistema SÍ detecta platform automáticamente** (`platform.system()` → "Linux" / "Windows"). Pero NO hay mapping automático platform → rol (primary/secondary). Eso se setea manualmente via `KAIROS_NODE_ROLE=primary` en `.env` o entorno.

**Lo que NO tiene:**
- No hay noción de "laptop" vs "PC grande" como identidad semántica. `node_id` es el hostname. Si el hostname es "maurol-laptop" o "maurol-PC", funciona, pero es accidental — no hay configuración que diga "este nodo es la laptop".
- No auto-configura el rol basado en platform o capacidad. Si querés que la PC grande sea primary por defecto, hay que setear `KAIROS_NODE_ROLE=primary` en su `.env`.

### 1.3 Embedding service — ✅ IMPLEMENTADO (fastembed ONNX)

`src/memory/embeddings/service.py`:
- Modelo: `paraphrase-multilingual-MiniLM-L12-v2-cls` (384 dimensiones, ~220 MB ONNX)
- Servicio singleton thread-safe con `RLock`
- `generate_embedding(text)` y `generate_embeddings_batch(texts)` para batching (3-5x más rápido)
- Fallback graceful: si el modelo falla, devuelve zero vectors y search sigue funcionando con keywords + entities
- `unload_if_idle()` para liberar RAM (timeout default: nunca — `999999.0` segundos)

**El modelo SÍ está cargado y funcionando** — ver el error en los tests: `ModuleNotFoundError: No module named 'fastembed'` significa que está instalado en el venv pero no en el sistema.

### 1.4 Memory write queue + lease — ✅ IMPLEMENTADO

`src/coordination/`:
- `memory_write_queue.py` — cola persistente de escrituras deferidas (secondary → queue → primary → flush)
- `leader_lease.py` — lease de liderazgo con TTL (evita dual primary)
- `memory_lease.py` — lease para escritura exclusiva de memoria
- `node_state.py` — coordinación de heartbeat, role, peer tracking

**El flujo SÍ funciona:** secondary encola escritura → primary/retry flushes → marcar sync. Las pruebas en `test_node_coordination.py` (27 tests) verifican promote/flush/restart/recovery.

### 1.5 Work catalog incremental — ✅ IMPLEMENTADO

`MemoryWorkCatalogRepository.max_processed_idx()` permite **vectorización incremental**:
```python
# max_processed_idx() → "resume desde aquí"
# is_processed() → "ya hice este item?"
# mark() → registrar resultado
```

El pipeline `vectorize_session()` ya usa esto con `_get_last_vectorized_idx()` — NO reprocesa exchanges ya vectorizados.

---

## 2. Problemas REALES detectados (verificados en código)

### 2.1 🔴 CRÍTICO — Dedup espor nodo, no cross-nodo

**Problema:** `vec_meta.content_hash` y `memory_work_catalog` viven en `memory.db` (una por nodo). Un texto vectorizado en la laptop genera un embedding en SU `memory.db`. Si la sincronización LAN replica ese texto a la PC grande, la PC grande **NO ve el content_hash** en su propia `memory.db` y recalcula el embedding.

**Irritación declarada por Mauro:** *"si ya se calcula un embedding durante una operación en vivo, después no debería recalcularse durante la síntesis o vectorización nocturna como si fuera texto nuevo."*

**Existe DENTRO de un nodo:** el pipeline `vectorize_session()` consulta `vec_meta.content_hash` antes de embeder (línea 438). Si el mismo texto está en dos sesiones del mismo nodo, NO se recalcula.

**NO existe CROSS-NODO:** no hay shared manifest, no hay consulta remota de content_hash, no hay protocolo de "ya tengo este embedding, no me lo mandes".

**Costo real:** el modelo ONNX tarda ~50-100ms por embedding. En una noche de curación con 1000 exchanges, 200 duplicados = 10-20s desperdiciado. No es catastrófico pero es trabajo pago que se pierde.

### 2.2 🔴 CRÍTICO — Las 3 DBs tienen identidad ambigua

| DB | Path real | ¿Qué es? | ¿Se sincroniza? |
|---|---|---|---|
| `sessions.db` | `memory/kairos_memory.db` | Sesiones/mensajes locales | NO (local por diseño) |
| `memory.db` (datos) | `data/kairos_memory.db` | Vectores, entidades, grafo, catalogos | SÍ (via Syncthing) |
| `memory.db` (curada) | `data/kairos_curated_memory.db` | Cache de memoria curada | SÍ |

**El problema de los nombres:** la DB local se llama `kairos_memory.db` pero vive en `memory/` y contien sessions — no es la "memory" global. La DB global se llama IGUAL (`kairos_memory.db`) pero vive en `data/` y tiene vectores — es la "memory" real. La tercera DB se llama `kairos_curated_memory.db` y es cache.

Un nuevo nodo o dev que ve el filesystem no puede distinguir cuál es cuál sin leer `db_path.py` y `memory_db_path.py`.

**El renombrado** (`kairos_memory.db` local → algo claro como `kairos_sessions.db`) está pendiente y es **RIESGO ALTO** porque rompe el path configurado en cada `.env` y/o la convención de paths. Si se renombra mal, los peers con el path viejo no encuentran la DB.

### 2.3 🟡 MEDIO — Entidades y clusters no tienen origin_node_id

`src/memory/entity/` y `src/memory/clustering/`:
- Las tablas `entities`, `relations`, `clusters`, `exchange_clusters` viven en `memory.db` (global syncable)
- NO tienen columna `origin_node_id` ni `node_id`
- Si dos nodos extraen la entidad "Python" del mismo texto en sus sesiones locales, ambos escriben un `INSERT OR IGNORE INTO entities(name='Python')` — se deduplica por `name UNIQUE`, OK
- PERO: si un nodo mergea `memory.db` via Syncthing, puede haber **conflictos de merge** en las filas de `clusters` o `exchange_clusters` porque no hay identity canónica de "este cluster nació en la laptop vs en la PC"

**Costo real:** conflictos de Syncthing en `memory.db` cuando dos nodos corren curator concurrente. Hoy se resuelve con "un dispositivo a la vez" (documentado en MEMORY.md), pero es un parche operacional, no técnico.

### 2.4 🟡 MEDIO — Sesiones federadas no tienen autoridad canónica

`web/routers/sessions.py` y `src/coordination/lan_bridge.py`:
- `request_session_directory()` mergea sesiones locales + remotas via `merge_session_entries()`
- El `source_mode` ("local" / "peer") distingue origen
- PERO: si la laptop crea sesión `abc-123` y la PC grande también crea `abc-123` (colisión de UUIDs, improbable pero posible), el merge no detecta conflicto — **simplemente aparecen dos entradas**

**El problema de los "nombres extraños"** que Mauro reportó probablemente viene de acá: sesiones que aparecen duplicadas en el sidebar con IDs similares pero distintos `source_url`, o sesiones que cambiaron de nombre localmente y el federated merge conserva el viejo.

**Falta:** un campo `origin_node_id` en `sessions` para que el merge pueda decir "esta sesión nació en la laptop, la PC es espejo, el nombre canonico es el de la laptop". Hoy el merge suma y ordena, no reconcilia.

### 2.5 🟡 MEDIO — Ventorización de sesiones no tiene backpressure

`src/memory/vectorize_sessions.py`:
- `vectorize_session()` procesa todos los exchanges de una sesión en batch
- `generate_embeddings_batch()` no tiene límite de batch size — si una sesión tiene 200 exchanges, manda los 200 textos al modelo de una
- En la laptop (menos RAM/CPU), esto puede causar **memory pressure** o timeout

**El roadmap ya detectó esto:** *"La laptop puede sufrir con embeddings o indexado en vivo cuando la conversación es larga o textual"* — Fase 3 del ROADMAP_DISTRIBUTED_KAIROS.md.

### 2.6 🟢 BAJO — `content_hash` usa MD5 (no criptográficamente seguro)

`src/memory/content_hash.py`:
```python
def content_hash(text: str, *, limit: int = 4000) -> str:
    return hashlib.md5(normalize_for_content_hash(text[:limit]).encode()).hexdigest()
```
Para dedup de embeddings, MD5 es suficiente (no hay adversario). Pero si en el futuro se quiere verificar integridad de manifest remoto, conviene SHA-256.

### 2.7 🟢 BAJO — `EmbeddingService` es module-level singleton

`src/memory/embeddings/service.py`:
```python
_service: EmbeddingService | None = None  # ← module-level global
_service_lock = threading.Lock()
```
Viola la regla "No global singletons" de AGENTS.md. Existe `configure_model()` y `reset_model()` para DI, pero `get_service()` crea el singleton lazy si no está configurado. En la práctica funciona porque el modelo es thread-safe, pero no es testeable en isolación sin mockear el módulo.

### 2.8 🟡 MEDIO — Renombramiento de DBs pendiente (riesgo alto)

`docs/REFACTOR_PENDING.md` lo lista como único ítem pendiente:
> Renombrar DBs (`kairos_memory.db` ↔ `kairos_curated_memory.db`) — 1h — Alto (rompe sync LAN si se hace mal)

**El riesgo es real:** si renombrás la DB local de `kairos_memory.db` a `kairos_sessions.db`, cualquier otro nodo que tenga `KAIROS_SESSIONS_DB_PATH` apuntando al path viejo no la encuentra. Hay que coordinar el rename en todos los `.env` de todos los nodos antes del siguiente heartbeat.

---

## 3. Decisión arquitectónica pendiente — el slice grande

Mauro identificó correctamente que sessions duplicadas + memoria sin identidad canónica + embeddings recálculados son **síntomas del mismo problema**: **los datos no tienen identidad canónica entre nodos**.

### El problema raíz

Hoy cada nodo es autónomo: tiene su `sessions.db` (local), su `memory.db` (global syncable), su `vec_meta`, su `memory_work_catalog`. La sincronización LAN replica eventos y snapshot, pero **no hay un manifest compartido que diga "este content_hash ya tiene embedding en el nodo X"**.

Arreglar solo memoria es装修 cosmético — los síntomas vuelven porque nuclean en un solo缺口.

### El slice propuesto (no iniciar sin diseño deliberado)

1. **`embedding_manifest` compartido** — tabla o estructura que vive en `memory.db` (global) con:
   - `content_hash` (ya existe en `vec_meta.content_hash`)
   - `source_node_id` (NUEVO)
   - `source_kind`: message, memory, summary, widget
   - `source_id`: session_id, memory_key, etc
   - `model`: nombre del modelo embedding (ya que diferentes modelos generan diferentes vectores)
   - `dimensions`: 384 (por si cambia el modelo)
   - `vector_store_id`: rowid en vec_meta
   - `status`: ready, pending, stale, failed (ya existe en work_catalog)
   - `created_at`, `updated_at`

   **Regla:** antes de embedir (en cualquier nodo), consultar el manifest. Si existe content_hash + model + dimensions → reutilizar. Si no → generar y registrar.

2. **Identidad canónica de sessions** — agregar `origin_node_id` a `sessions` para que el federated merge reconcilie en vez de sumar.

3. **Servicio de embeddings remoto (Fase 3)** — `POST /api/node/embedding/jobs`: laptop envía lote de textos pendientes, PC grande embede y devuelve resultados. Idempotente via manifest.

4. **Renombrado de DBs** — solo después de (1)-(3), cuando el sistema tenga identidad canónica de todo lo compartido.

### Por qué NO hacerlo ahora

- Es un slice arquitectónico, no un parche.
- Requiere migración de schema en `memory.db` (todos los nodos).
- Requiere protocolo de replica deliberado (no solo Syncthing event-driven).
- Requiere pruebas de campo con dos nodos reales (laptop + PC).
- Hacerlo fumado a las 4am = bugs sutiles que duelen semanas.

---

## 4. Contrato cross-node — protocolo de dedup compartido

El contrato está documentado por `tests/unit/test_cross_node_dedup.py` (5 tests, todos passing). Sus reglas son **invariantes del sistema** — cualquier cambio futuro que rompa uno de estos tests es una regresión arquitectónica.

### Reglas del contrato

1. **`vec_meta.content_hash` es la clave de dedup.** La query `SELECT rowid FROM vec_meta WHERE content_hash = ?` NO filtra por `source_node_id`. Eso significa que **cualquier vector con el mismo texto normalizado es considerado duplicado**, sin importar quién (qué nodo) lo escribió.

2. **`source_node_id` es metadata, no filter.** Sirve para que el curator y el manifest sepan "quén pagó el embedding", pero NO afecta la lógica de dedup. Dos nodos que escriben el mismo content_hash convergen a una fila (la última gana vía INSERT OR REPLACE del work_catalog, o el catalog la marca como `deduped` con `vec_rowid` apuntando a la fila existente).

3. **`origin_node_id` en sessions y entities es advisory reconciliation.** Cuando dos nodos federan sesiones (fallback sidebar merge), `origin_node_id` permite que el merge reconcilie en vez de sumar — pero el primer paso es solo documentarlo; el merge actual sigue sumando. La Fase 4 (próxima) usará esta columna para reconciliar.

4. **`memory.db` es la fuente de verdad compartida.** Una vez que Syncthing replica `memory.db` entre dos nodos, el contrato se cumple automáticamente: cada nodo ve los `vec_meta` rows del otro, y el dedup funciona cross-nodo sin código nuevo. El manifest (Fase 6 del ROADMAP_DISTRIBUTED_KAIROS.md) solo necesita hacer la consulta **remota** antes de que Syncthing sync ocurra, no cambiar el storage layer.

### Invariantes verificadas

| Test | Verifica |
|---|---|
| `test_source_node_id_column_persisted` | Migration 015 bifurca `vec_meta.source_node_id` |
| `test_entities_origin_node_id_column` | Migration 016 bifurca `entities.origin_node_id` |
| `test_clusters_origin_node_id_column` | Migration 017 bifurca `topic_clusters.origin_node_id` |
| `test_vectorstore_insert_persists_source_node_id` | `VectorStore.insert` escribe `source_node_id` correctamente |
| `test_cross_node_dedup_finds_peer_embedding_via_content_hash` | **Core:** un nodo encuentra embeddings escritos por otro nodo vía content_hash lookup |

### Qué este contrato NO cubre aún

- **Lookup remoto sincrónico:** si el texto aún no se sincronizó via Syncthing, el nodo B no lo ve. El manifest futuro (Fase 3 del ROADMAP) haría `GET /api/node/embedding-lookup?content_hash=X` antes de embedir.
- **Conflicto de merged rows:** si dos nodos escriben el MISMO content_hash con diferentes `source_key` (session_ids distintos), solo queda la última fila en `vec_meta`. El `memory_work_catalog` sin embargo trackea ambos items (`source_key, item_idx`), y uno queda marcado como `deduped` apuntando al `vec_rowid` de la otra. **No hay pérdida de información de provenance.**
- **Model versioning:** si se cambia el modelo embedding (ej: de MiniLM a uno multilingual mejor), todos los content_hashes siguen iguales pero los vectores serían incompatibles. Falta una columna `model` en `vec_meta` para filtros cross-model. Hoy hay un solo modelo (`paraphrase-multilingual-MiniLM-L12-v2-cls`), no es urgente.

---

## 5. Estado de implementación — Fases 1-4 COMPLETADAS (2026-06-29)

### Fase 1 — Schema migrations ✅

Tres migraciones aditivas (sessions.db migration 025 + memory.db migrations 015-017), todas con `DEFAULT ''` (backwards-compat). Viejos path funcionan sin tocar nada. Verificado con `init_db()` y `init_memory_db()` en DBs temporales.

- `sessions.origin_node_id` (TEXT DEFAULT '') + index `idx_sessions_origin_node_id`
- `vec_meta.source_node_id` (TEXT NOT NULL DEFAULT '') + index `idx_vec_meta_source_node`
- `entities.origin_node_id` (TEXT NOT NULL DEFAULT '') + index `idx_entities_origin_node`
- `topic_clusters.origin_node_id` (TEXT NOT NULL DEFAULT '') + index `idx_topic_clusters_origin_node`

`schema_version=25`, `memory_schema_version=17`.

### Fase 2 — Provenance populated at write-time ✅

4 entry points stamp `origin_node_id` / `source_node_id` en cada escritura:

| Site | Cambio |
|---|---|
| `VectorStore.insert(...)` | Nuevo param `source_node_id`. Insert con columna nueva (fallback al INSERT legacy si el schema es viejo). Safety-net `ALTER TABLE` agregregado a `_init_tables()`. |
| `SessionRepository.ensure(session_id, *, origin_node_id="")` | INSERT con `origin_node_id`. Caller lo resolve desde `peek_node_coordinator().node_id`. |
| `EntityRepository.upsert_entity(...)` (usado por `flush_entities_to_db`) | INSERT/ON CONFLICT actualiza `origin_node_id`. Schema probe antes de INSERT (fallback si migration no corrió). |
| `flush_clusters_to_db(clusterer, db_path, mappings, *, origin_node_id="")` | INSERT de `topic_clusters` con column nueva. Schema probe. UPDATE también la propaga. |
| `vectorize_session(...)` y `vectorize_all_sessions(...)` | Aceptan `source_node_id` ylo pasan a `VectorStore.insert` (2 paths: single exchange + batch) y a `flush_*`. |
| `src/memory/provenance.py` | Helper `resolve_local_node_id()` que lee `peek_node_coordinator()` con try/except. Cero acoplamiento de memory a coordination: el import es lazy y gracefully degrada a `""` sin coordinator. |
| `src/api/session.py:ensure_session` | Resuelve node_id al nivel API (no en storage) y lo pasa al repos. |
| `web/routers/chat.py:95` | Mismo patrón: `_resolve_origin_node_id()` inline (helper local, como en src/api/session.py) y pasa a `repos.sessions.ensure`. |

### Fase 3 — Contrato cross-node testado ✅

Nuevo archivo `tests/unit/test_cross_node_dedup.py` (5 tests):

1. `test_source_node_id_column_persisted` — migration 015 aterrizó
2. `test_entities_origin_node_id_column` — migration 016 aterrizó
3. `test_clusters_origin_node_id_column` — migration 017 aterrizó
4. `test_vectorstore_insert_persists_source_node_id` — INSERT escribe la columna
5. `test_cross_node_dedup_finds_peer_embedding_via_content_hash` — **El test clave del contrato**: un nodo encuentra el embedding escrito por OTRO nodo via la query `SELECT rowid FROM vec_meta WHERE content_hash = ?`. No filter por `source_node_id` — el dedup cross-nodo es automático una vez que `memory.db` se replica.

Invariante del contrato: `source_node_id` es metadata, no filter. Cualquier test futuro que rompa este invariante es una regresión arquitectónica.

### Fase 4 — Federated session reconciliation ✅

Symptom de Mauro (`"sessions duplicadas / nombres extraños"`) arrglado en el layer concordante:

- `SessionRepository.get_all()` ahora SELECT `COALESCE(s.origin_node_id, '')` (con schema probe para DBs pre-migration-025).
- `session_summary_from_row()` extrae `origin_node_id` del row tuple y lo populate en el entry dict.
- `merge_session_entries()` reescrito: dedup por `sid` (no por `(sid, node_id, source_url)`), con priority al entry cuyo `node_id` == `origin_node_id` (el owner canonical). Fallback a `last_seen_at` cuando origin es desconocido.

Nuevo archivo `tests/unit/test_session_reconciliation.py` (5 tests):

1. `test_merge_dedup_keeps_one_per_sid` — misma sesión en dos peers colapsa a 1 entry
2. `test_merge_prefers_entry_whose_node_id_matches_origin_node_id` — el que creó la sesión gana
3. `test_merge_falls_back_to_latest_activity_when_origin_unknown` — legacy rows fallback al más reciente
4. `test_merge_distinct_sids_keep_all` — sids distintos no se mergean
5. `test_merge_preserves_favorite_flag_from_canonical_owner` — favorite del dueño, no del peer

### Fase 5 — Renombramiento de DBs — DEFERRED ⏳

Sigue pendiente como único item sin tocar. Requiere coordinación online de `.env` en todos los peers. No se hace en esta sesión.

### Tests result

| Suite | Tests | Status |
|---|---|---|
| node_coordination | 27 | ✅ |
| memory_router | 7 | ✅ |
| sessions_router | 7 | ✅ |
| pages_router | 14 | ✅ |
| anti_regression | 34 | ✅ |
| regression_pipeline | 53 | ✅ |
| memory_repos | 64 | ✅ |
| cross_node_dedup (NEW) | 5 | ✅ |
| session_reconciliation (NEW) | 5 | ✅ |
| vectorize_sessions (venv) | 13 | ✅ |
| vector_store (existing) | 11 | ✅ |

Total: 240 tests verificados post-cambio. 0 regresiones.

---

## 6. Inventario rápido (lo que existe hoy)

| Componente | Archivo | Estado |
|---|---|---|
| Content hash (MD5 normalizado) | `src/memory/content_hash.py` | ✅ Funcional |
| VectorStore (sqlite-vec) | `src/memory/vector/store.py` | ✅ Funcional, thread-safe |
| Embedding service (fastembed ONNX) | `src/memory/embeddings/service.py` | ✅ Funcional (module singleton) |
| Work catalog (dedup tracking) | `src/memory/repos_memory/work_catalog_repo.py` | ✅ Funcional |
| Vectorización incremental | `src/memory/vectorize_sessions.py` | ✅ Funcional (batch + dedup + resume) |
| Noise filter | `src/memory/noise_filter.py` | ✅ Funcional |
| Keyword extractor (TF-IDF) | `src/memory/keywords/` | ✅ Funcional |
| Entity extractor + graph | `src/memory/entity/` | ✅ Funcional |
| Clustering heurístico | `src/memory/clustering/` | ✅ Funcional (Jaccard) |
| Hybrid retrieval (vector+keyword+entity) | `src/memory/retrieval/` | ✅ Funcional (RRF fusion) |
| Node coordinator (heartbeat+role) | `src/coordination/node_state.py` | ✅ Funcional |
| LAN bridge (peer discovery+requests) | `src/coordination/lan_bridge.py` | ✅ Funcional |
| Leader lease (TTL exclusive) | `src/coordination/leader_lease.py` | ✅ Funcional |
| Memory write queue (persistent) | `src/coordination/memory_write_queue.py` | ✅ Funcional |
| Memory snapshot + compare | `web/routers/_memory_snapshot.py` | ✅ Funcional |
| Failover state machine | `web/services/failover_state.py` | ✅ Funcional |
| **embedding_manifest cross-nodo** | — | ❌ NO EXISTE |
| **origin_node_id en sessions** | — | ❌ NO EXISTE |
| **origin_node_id en entities/clusters** | — | ❌ NO EXISTE |
| **Batch size limit en vectorize_session** | — | ❌ NO EXISTE |
| **DB rename** | — | ❌ PENDIENTE (alto riesgo) |
| **Servicio de embeddings remoto** | — | ❌ NO EXISTE (Fase 3 roadmap) |

---

## 7. Orden recomendado cuando se decida encarar (Fase 5 y futuro)

1. **`embedding_manifest` con source_node_id** — prerequisito de todo lo demás. Tabla compartida en `memory.db` con content_hash + node_id + model + status. Consulta cross-nodo antes de embedir.
2. **Servicio de embeddings remoto (Fase 3)** — `POST /api/node/embedding/jobs`. Laptop delega, PC grande procesa, manifest evita recalcular.
3. **`origin_node_id` en sessions** — migración de schema. Federated merge reconcilia en vez de sumar.
4. **`origin_node_id` en entities/clusters** — misma idea. Evita conflictos de Syncthing cuando dos nodos corren curator.
5. **Batch size limit en vectorize_session** — protección para laptop. `max_batch_size=32` o configurable.
6. **Renombrado de DBs** — solo después de todo lo anterior, cuando la identidad canónica esté consolidada.

**No iniciar sin:** sueño, dos nodos reales para probar, y cabeza fría.