# Kairos sync protocol

Fecha: 2026-06-29

Este documento define el contrato operativo para sincronizacion LAN, memoria,
catalogos y embeddings multi-nodo. La meta es que Kairos pueda correr en varias
maquinas sin duplicar trabajo caro, sin compartir SQLite crudos entre writers, y
sin perder trazabilidad de donde salio cada derivado.

## Estado actual verificado

Al 2026-06-29, el protocolo basico esta sano:

- PC principal: `pc-principal`, rol `primary`, Windows, `http://192.168.1.35:8000`.
- Laptop: `pc-secundaria`, rol `secondary`, Linux, `http://192.168.1.38:8000`.
- Ambos repos estan en el mismo commit cuando se corre el doctor LAN.
- `lan-doctor` valida health, runtime, sync, failover, memoria y smoke de escritura.
- `memory-preflight` valida catalogos locales y remotos.
- `sessions.db` es local por nodo.
- `kairos_curated_memory.db` contiene derivados consultables y catalogos.
- `MEMORY.md` sigue siendo source of truth humano/curado.

Resultados esperados en un sistema sano:

- `memory_audit.ok == true` en cada nodo.
- `memory_work_catalog` existe y no tiene links rotos.
- `memory_processing_catalog` existe y no tiene `failed` ni `stale`.
- `vec_meta` no tiene duplicados por `content_hash`.
- `sessions.db` no tiene tablas vectoriales legacy.
- Las diferencias de cantidad de sesiones/mensajes entre nodos son normales.

## Capas de datos

### 1. Memoria curada

Archivo: `MEMORY.md`

Rol:

- Source of truth semantico de largo plazo.
- Texto sincronizable y recuperable ante conflictos.

Regla:

- Solo el primary debe aceptar escrituras directas cuando hay peers LAN.
- El secondary delega a `/api/node/memory/request`.
- Si el primary no esta disponible, el secondary encola en `memory_write_queue`.

### 2. Memoria estructurada sincronizable

Archivo: `memory/kairos_curated_memory.db`

Rol:

- Indices derivados: `memory_index`, `vec_meta`, keywords, entidades, clusters,
  catalogos y sintesis.
- Reconstruible parcialmente desde `MEMORY.md` y `sessions.db` locales.

Regla:

- No se debe tratar como base transaccional compartida por dos writers.
- Las escrituras LAN deben pasar por primary, leases o jobs idempotentes.
- Todo derivado debe tener hash de contenido y procedencia.

### 3. Sesiones locales

Archivo: `memory/kairos_memory.db`

Rol:

- Conversaciones crudas, tool calls, widgets, debug y estado episodico local.

Regla:

- No se sincroniza entre nodos.
- No se copia completa al primary.
- La identidad federada se resuelve con `session_id + origin_node_id`.

## Identidad y procedencia

Campos canonicos:

- `sessions.origin_node_id`: nodo donde nacio la sesion.
- `vec_meta.source_node_id`: nodo que produjo el embedding.
- `entities.origin_node_id`: nodo que extrajo la entidad.
- `topic_clusters.origin_node_id`: nodo que propuso el cluster.

Reglas:

- `origin_node_id` identifica ownership logico.
- `source_node_id` identifica quien hizo trabajo derivado.
- Si el campo esta vacio, la fila es legacy u origin unknown.
- La federacion de sidebar debe deduplicar por `session_id` y preferir la fila
  cuyo `node_id == origin_node_id`.

## Unidad idempotente

La unidad idempotente no es una sesion completa ni un message id.

Unidad base:

```text
source + source_key + item_idx + content_hash + pipeline + model_id + pipeline_version
```

Estado actual:

- `memory_work_catalog` cubre `source + source_key + item_idx + content_hash`.
- `memory_processing_catalog` cubre `source + source_key + item_idx + stage + content_hash`.

Proximo ajuste:

- Extender catalogos o metadata para incluir `pipeline`, `pipeline_version`,
  `model_id`, `model_version` y `source_node_id`.

## Catalogos

### `memory_work_catalog`

Pregunta que responde:

```text
Este item logico ya fue vectorizado, deduplicado o descartado como ruido?
```

Estados validos:

- `embedded`: se genero vector nuevo.
- `deduped`: se reutilizo un vector existente por `content_hash`.
- `noise`: se descarto por ruido o texto corto.
- `pending`: reservado para cola futura.
- `failed`: reservado para cola futura.

Regla:

- Este catalogo no autoriza saltar curacion LLM.
- Solo cubre trabajo de vectorizacion.

### `memory_processing_catalog`

Pregunta que responde:

```text
Esta etapa semantica cara ya proceso esta entrada exacta?
```

Etapas actuales:

- `curation_candidate`: inventario de sesiones vectorizadas.
- `curated`: curacion LLM real de una sesion.
- `generated`: sintesis diaria.

Estados:

- `observed`: inventario, no significa procesado.
- `processed`: etapa completada.
- `skipped`: etapa omitida de forma valida.
- `failed`: fallo y debe aparecer en preflight.

Regla:

- `observed` nunca debe usarse para saltar LLM.
- Si cambia el prompt, modelo, pipeline o contenido, debe cambiar el hash de
  decision y se puede reprocesar.

## Flujo actual de una sesion local

1. El usuario escribe en un nodo.
2. `sessions.ensure()` crea la sesion con `origin_node_id`.
3. `messages.save_record()` persiste mensajes crudos localmente.
4. Al cerrar o interrumpir stream, se agenda vectorizacion en background.
5. `vectorize_session()` agrupa user+assistant en exchanges.
6. Para cada exchange calcula `content_hash`.
7. Si el catalogo ya cubre ese hash para ese item, lo salta.
8. Si otro vector tiene ese `content_hash`, marca `deduped`.
9. Si no existe, genera embedding y marca `embedded`.
10. Auditoria verifica faltantes, stale vectors, duplicados y links rotos.

Compatibilidad legacy:

- Si no hay catalogo, `vectorize_session()` todavia usa `MAX(exchange_idx)` como
  fallback. El protocolo nuevo debe considerar eso solo modo legado.

## Flujo actual de memoria curada

1. `save_memory` en primary escribe `MEMORY.md`.
2. Actualiza `memory_index`.
3. Genera embedding `source='memory'` en `vec_meta`.
4. Marca revision/sync en el coordinador.
5. Publica eventos LAN.

Estado implementado:

- El embedding de `source='memory'` queda registrado en `memory_work_catalog`
  con identidad de pipeline/modelo.
- Si el embedding ya estaba vigente, `save_memory` no recalcula pero igualmente
  marca la unidad como cubierta.

## Protocolo para embeddings remotos

Objetivo:

- La laptop conserva sesiones crudas.
- La PC principal puede calcular embeddings pesados.
- Nadie copia `sessions.db`.
- Nadie abre SQLite remoto con dos writers.

Endpoint implementado:

```text
POST /api/node/embeddings/jobs
GET  /api/node/embeddings/queue
POST /api/node/embeddings/flush
```

Payload:

```json
{
  "source": {"node_id": "pc-secundaria"},
  "items": [
    {
      "source": "session",
      "source_key": "local-session-id",
      "item_idx": 12,
      "content_hash": "abc123",
      "text": "User: ...\nAssistant: ..."
    }
  ]
}
```

Respuesta:

```json
{
  "ok": true,
  "queued": false,
  "duration_ms": 12.3,
  "processed": [
    {
      "source": "session",
      "source_key": "local-session-id",
      "item_idx": 12,
      "status": "embedded",
      "vec_rowid": 1234
    }
  ]
}
```

Reglas:

- El primary descarta hashes ya cubiertos por `content_hash + model_id +
  pipeline_version`.
- Si el receptor no es primary, encola en `embedding_job_queue`.
- `POST /api/node/embeddings/flush` procesa la cola cuando el nodo es primary.
- `NodeLanBridge.request_embedding_jobs()` es el cliente LAN para entregar jobs
  al primary.
- `NodeLanBridge.replay_pending_embedding_jobs()` reintenta trabajos pendientes
  contra el primer primary reachable.
- La cola distingue `pending`, `retryable` y `failed`, con `attempts` y
  `last_error`.
- `dry_run=true` valida el contrato HTTP sin generar embeddings ni tocar
  `vec_meta`.

## Doctor obligatorio

Antes de considerar sano un nodo remoto:

```bash
python ops/remote/kairos_remote.py doctor --node linux
```

Antes de considerar sano el cluster:

```bash
python ops/remote/kairos_remote.py lan-doctor --node linux --primary-url http://192.168.1.35:8000 --secondary-url http://192.168.1.38:8000
```

Antes de confiar en catalogos:

```bash
python ops/remote/kairos_remote.py memory-preflight --node linux
```

Criterio de aprobado:

- Remote doctor: todos los checks pasan.
- LAN doctor: todos los checks pasan, incluido smoke de memoria.
- LAN doctor incluye `remote_embedding_job_dry_run`.
- Memory preflight: todos los nodos `ok`.
- Los bloques `[DIFF]` de volumen no son failure si ambos nodos estan `ok`.

## Invariantes que deben tener tests

- Crear una sesion nueva estampa `origin_node_id`.
- Federar sesiones deduplica por `session_id` y respeta canonical owner.
- Dos exchanges con mismo `content_hash` no generan dos embeddings.
- Un exchange cambiado deja de estar cubierto por el catalogo anterior.
- Un `vec_rowid` roto en catalogo aparece en auditoria/preflight.
- `save_memory` en secondary delega o encola, no escribe directo.
- LAN smoke escribe en primary y el secondary puede ver la memoria.
- `observed` en processing catalog no salta curacion LLM.

## Riesgos restantes

1. La auditoria de calidad semantica es inicial: detecta vacios, cortos,
   timestamps faltantes y duplicados exactos; falta scoring semantico mas fino.
2. Falta aplicar automaticamente resultados remotos en un catalogo local
   separado cuando el solicitante quiera conservar evidencia propia, aunque el
   primary ya registra la unidad remota con `source_node_id`.

## Frontera scripts vs funciones del sistema

Regla general:

- Si la logica inspecciona o repara estado interno de memoria, debe vivir en
  `src/memory/maintenance/` y exponer una funcion importable.
- Si la logica prueba el sistema desde afuera por HTTP, SSH o control de
  servicios, puede vivir en `scripts/` u `ops/remote/`.
- `scripts/` debe ser una fachada CLI fina: parsea argumentos, llama funciones
  de sistema, imprime salida y define exit code.
- `ops/remote/` debe quedarse como borde operativo: perfiles, SSH, HTTP remoto,
  reportes humanos y comandos de campo.

Clasificacion actual:

| Archivo | Estado recomendado | Motivo |
| --- | --- | --- |
| `scripts/memory_audit.py` | wrapper CLI hacia `src/memory/maintenance/audit.py` | `run_audit()` es logica de dominio reutilizable por doctor, UI y tools. |
| `scripts/backfill_processing_catalog.py` | wrapper CLI hacia `src/memory/maintenance/backfill_processing_catalog.py` | `run_backfill()` modifica catalogos y ya es parte del preflight real. |
| `scripts/memory_repair.py` | wrapper CLI hacia `src/memory/maintenance/repair.py` | `plan_repairs()`, `apply_catalog_repairs()` y `vectorize_missing()` son mantenimiento interno. |
| `scripts/memory_pipeline_preflight.py` | wrapper CLI hacia `src/memory/maintenance/pipeline_preflight.py` | `run_local_pipeline()` y `node_snapshot()` son contrato del sistema; el runner remoto puede quedar inyectado. |
| `scripts/cleanup_legacy_session_vectors.py` | dejar como script de migracion o mover a maintenance si se reutiliza | Es una limpieza historica, no flujo diario. |
| `scripts/backfill_content_hash.py` | dejar como migracion legacy si ya no corre | Backfill puntual de schema viejo. |
| `scripts/lan_field_smoke.py` | mantener como edge script | Debe probar endpoints publicos desde afuera; no conviene importarlo en runtime. |
| `scripts/lan_failover_drill.py` | mantener como edge script | Controla servicios y simula outage; es operacion de campo. |
| `ops/remote/kairos_remote.py` | mantener en ops, extraer modelos si crece | SSH/HTTP remoto es frontera operativa, no dominio de memoria. |

Forma objetivo:

```text
src/memory/maintenance/
  audit.py
  repair.py
  backfill_processing_catalog.py
  pipeline_preflight.py

scripts/
  memory_audit.py                 # wrapper CLI
  memory_repair.py                # wrapper CLI
  backfill_processing_catalog.py  # wrapper CLI
  memory_pipeline_preflight.py    # wrapper CLI

ops/remote/
  kairos_remote.py                # SSH/HTTP edge orchestration
```

API interna objetivo:

```python
from src.memory.maintenance.audit import run_audit
from src.memory.maintenance.repair import plan_repairs, apply_catalog_repairs
from src.memory.maintenance.backfill_processing_catalog import run_backfill
from src.memory.maintenance.pipeline_preflight import run_local_pipeline, build_pipeline_report
```

Reglas de migracion:

- No romper comandos existentes; cada script viejo debe seguir funcionando.
- Primero mover codigo sin cambiar comportamiento.
- Despues apuntar `ops/remote/kairos_remote.py` al modulo nuevo.
- Luego agregar endpoints/tools que llamen el modulo, no el script.
- Evitar que `src/` importe `scripts/`.

## Proximo corte recomendado

1. Subir la auditoria de calidad de memorias curadas de heuristica a scoring
   semantico real.
2. Decidir si el solicitante remoto debe guardar una copia local del resultado
   del job o si alcanza con el catalogo central del primary.
