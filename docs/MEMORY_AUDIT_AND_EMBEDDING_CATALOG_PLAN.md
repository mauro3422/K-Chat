# Auditoria de memoria y catalogo de embeddings

Fecha: 2026-06-27

## Objetivo

Unificar dos preocupaciones que estan conectadas:

1. La auditoria de memoria/sintesis, para saber por que se curan o reanalizan datos cuando no hubo actividad visible.
2. El catalogo de embeddings, para no recalcular ni reutilizar vectores stale sobre textos que ya cambiaron.

El objetivo no es meter otra capa pesada. El objetivo es que cada pieza del sistema pueda responder:

- que texto procese;
- con que hash;
- con que modelo;
- cuando;
- desde que nodo;
- con que resultado;
- si esa salida sigue vigente.

## Estado actual observado

### Escrituras de memoria curada

`save_memory` escribe en:

- `MEMORY.md`;
- `memory_index` dentro de `memory/kairos_curated_memory.db`;
- `vec_meta`/`vec_entries` para embeddings de fuente `memory`.

La escritura de memoria curada ya tiene lease LAN y eventos, pero el embedding que genera queda registrado solo como vector + metadata parcial.

### Vectorizacion de sesiones

`web/services/chat_stream.py` agenda vectorizacion al terminar el stream y tambien en el `finally`, incluso si hubo desconexion.

Telegram hace una vectorizacion parecida en `channels/telegram/adapter.py`.

`src/memory/vectorize_sessions.py` usa `MAX(exchange_idx)` en `vec_meta` para decidir desde donde continuar. Eso evita bastante trabajo repetido, pero tiene una limitacion importante: no prueba que el contenido actual del exchange siga siendo el mismo contenido que se vectorizo.

### Curator y sintesis

`curate_all()` hace:

1. `vectorize_all_sessions()` incremental;
2. gardener;
3. tracer;
4. curator por clusters y sesiones recientes;
5. checkpoint de curation;
6. daily synthesis.

La curacion de sesiones recientes usa `created_at >= now-days` y no una marca de "esta sesion/exchange ya fue curado hasta este hash". Por eso puede volver a pensar sobre la misma sesion durante varios dias si entra en la ventana.

### Hallazgo concreto local

En la PC grande:

- `memory/kairos_curated_memory.db` tiene `memory_index=193`, `vec_meta=16`.
- `vec_meta` global tiene `memory=10`, `session=6`.
- No hay grupos duplicados por `hash` o `content_hash`.
- La sesion local `ac5ca47f...` tiene 6 exchanges y 6 vectores, pero 2 hashes actuales no coinciden con los hashes guardados. Esto indica vectores stale o vectorizacion sobre una version previa/parcial del texto.
- Hay sesiones locales con exchanges sin vectores en `memory.db`.
- `memory/kairos_memory.db` todavia contiene tablas vectoriales con 12 vectores de fuente `session`, probablemente residuo/legado de etapas donde sesiones y memoria compartian mas infraestructura.

Salida del auditor local agregado en este corte:

```text
Kairos memory audit
sessions=7 messages=172 memory_entries=193
vectors=16 sources={"memory": 10, "session": 6}
issues: missing_sessions=3 stale_sessions=1 orphan_sources=0 dup_hash_groups=0 dup_content_hash_groups=0
legacy: sessions.db has vec_meta with 12 rows
synthesis: exists=False count=0 latest=-
```

### Hallazgo de bug probable

`src/memory/curator/curate.py` llama:

```python
mem_db = _get_memory_db_path()
synthesis_path = await generate_daily_synthesis(db_path=mem_db)
```

Pero `src/memory/synthesis/daily.py` espera que `db_path` sea `sessions.db` para leer tablas `sessions` y `messages`, y resuelve `memory.db` internamente. En esta PC no existe `memory/synthesis`, consistente con que la sintesis diaria no esta generando reportes locales o esta fallando y siendo atrapada por logs.

## Riesgos actuales

1. Stale vectors: un exchange puede cambiar despues de una vectorizacion parcial y quedar marcado como procesado por `exchange_idx`.
2. Recuracion: el curator puede volver a pasar por sesiones recientes porque no hay checkpoint por contenido.
3. Doble indice historico: existen tablas vectoriales en `sessions.db` y `memory.db`, lo que confunde auditorias y futuras sincronizaciones.
4. Falta de procedencia: los vectores no guardan de forma uniforme `model_id`, `model_version`, `node_id`, `source_db`, `content_hash`, `pipeline_version`.
5. Sintesis no idempotente: los reportes/checkpoints se guardan por fecha, pero no hay marca clara de inputs exactos incluidos.
6. Borrado demasiado amplio: `VectorStore.delete_by_source(source_key)` borraba por `source_key` sin filtrar `source`, con riesgo de borrar una sesion si una memoria compartia la misma key o viceversa.

## Diseno propuesto: catalogo de trabajo de memoria

Agregar a `memory/kairos_curated_memory.db` una tabla liviana, no acoplada al transporte LAN:

```sql
CREATE TABLE memory_work_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_node_id TEXT NOT NULL DEFAULT '',
    source_key TEXT NOT NULL DEFAULT '',
    source_message_id TEXT NOT NULL DEFAULT '',
    source_exchange_idx INTEGER NOT NULL DEFAULT -1,
    content_hash TEXT NOT NULL,
    content_len INTEGER NOT NULL DEFAULT 0,
    model_id TEXT NOT NULL DEFAULT '',
    model_version TEXT NOT NULL DEFAULT '',
    pipeline TEXT NOT NULL,
    pipeline_version TEXT NOT NULL DEFAULT '1',
    status TEXT NOT NULL DEFAULT 'done',
    vector_rowid INTEGER,
    result_key TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_type, source_node_id, source_key, source_exchange_idx, pipeline, content_hash)
);
```

`source_type` inicial:

- `memory_entry`: una entrada de `MEMORY.md`/`memory_index`.
- `session_exchange`: exchange user+assistant de `sessions.db`.
- `session_snapshot`: resumen derivado de una sesion remota.
- `curation_cluster`: cluster usado por curator.
- `daily_synthesis`: reporte generado.

`pipeline` inicial:

- `embed`;
- `keywords`;
- `entities`;
- `cluster`;
- `curate`;
- `synthesis`.

## Cambio de criterio

El sistema no deberia preguntar solamente:

"ya procese el exchange idx 5?"

Deberia preguntar:

"ya procese este contenido exacto, con este pipeline, este modelo y esta version?"

Si el texto cambia, cambia el `content_hash`, y el sistema sabe que el vector anterior es stale.

## Plan por fases

### Fase 1 - Auditoria sin cambiar comportamiento

Entregables:

- comando de diagnostico local: `manage_memory audit` o script `scripts/memory_audit.py`;
- reporte con:
  - vectores stale por sesion;
  - exchanges sin vector;
  - vectores huerfanos;
  - duplicados por `hash` y `content_hash`;
  - tablas vectoriales legacy en `sessions.db`;
  - estado de synthesis diaria;
  - ultimos checkpoints de curation.

Regla: solo lectura. No borra, no reindexa.

### Fase 2 - Catalogo minimo

Entregables:

- migracion `memory_work_catalog`;
- repositorio o helper de catalogo en `src/memory/`;
- registro al terminar `save_memory` embedding;
- registro al terminar `vectorize_session`;
- tests de idempotencia por `content_hash`.

Regla: el catalogo observa y registra; todavia no decide.

### Fase 3 - Revectorizacion correcta por hash

Entregables:

- reemplazar `MAX(exchange_idx)` como unica fuente de verdad;
- si `exchange_idx` existe pero el hash actual difiere, marcar viejo como stale y generar vector nuevo;
- si el hash ya existe con mismo pipeline/modelo, reutilizar o linkear sin recalcular;
- limpiar `vec_keywords`, clusters y entity_mentions asociados al rowid stale.

Regla: no borrar historico de golpe. Primero marcar stale; luego gardener limpia.

### Fase 4 - Curator idempotente

Entregables:

- catalogar cada input de curator por `content_hash`;
- no volver a pedir LLM para el mismo bloque de sesion/cluster si ya fue curado con esa version;
- guardar `result_key` para saber que memoria salio de que input;
- corregir `generate_daily_synthesis(db_path=sessions_db)`.

Regla: el LLM solo reanaliza si cambio el contenido, el prompt version, o el modelo/pipeline.

### Fase 5 - Separacion local/global para multi-nodo

Entregables:

- `source_node_id` obligatorio para session vectors;
- la PC grande puede catalogar embeddings de sesiones de laptop sin copiar `sessions.db`;
- laptop conserva sesiones crudas;
- PC grande guarda indices derivados y referencias `node_id + session_id + message_id/exchange_idx`.

Regla: sincronizar derivados, no bases SQLite abiertas por dos writers.

## Primeros cambios recomendados

1. Corregir el bug de daily synthesis: pasar `sessions_db` desde `curate_all()`.
2. Crear `scripts/memory_audit.py` con reporte solo lectura.
3. Agregar migracion de `memory_work_catalog`.
4. Registrar `save_memory` y `vectorize_session` en el catalogo, sin cambiar decisiones.
5. Reemplazar la decision incremental por hash despues de tener tests.

Estado del primer corte:

- [x] `curate_all()` pasa `sessions.db` a daily synthesis.
- [x] `scripts/memory_audit.py` genera reporte solo lectura.
- [x] `VectorStore.delete_by_source()` acepta `source` para borrar solo `memory` o solo `session`.
- [ ] `memory_work_catalog` pendiente.
- [ ] Decision incremental por `content_hash` pendiente.

## Criterio de aprobado

- Un comando muestra por que hay o no hay trabajo pendiente.
- Si un exchange cambia despues de vectorizarse, el sistema lo detecta.
- Si un exchange ya fue embebido con el mismo contenido/modelo, no se recalcula.
- El curator no vuelve a mandar al LLM el mismo bloque sin cambio real.
- La laptop puede delegar embeddings a la PC grande usando el mismo catalogo.
