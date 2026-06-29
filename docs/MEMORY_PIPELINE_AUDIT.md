# Auditoria de memoria y catalogos

Fecha: 2026-06-28

## Estado actual

Kairos ya tiene dos niveles distintos de catalogo:

- `memory_work_catalog`: responde si un item de sesion ya fue vectorizado o descartado como ruido.
- `memory_processing_catalog`: responde si una etapa semantica cara ya proceso una entrada exacta.

Esto evita dos duplicaciones distintas:

- recalcular embeddings de mensajes que ya tienen hash/vector;
- volver a pedir curacion o sintesis LLM si el contenido de entrada no cambio.

## Decision importante

No se debe marcar una sesion vieja como `curated/processed` solo porque ya tiene embeddings. Tener embeddings significa que se puede buscar semanticamente. No significa que el curador haya extraido memoria nueva o haya decidido `NO_NEW_INFO`.

Por eso el backfill historico usa:

- `session + curation_candidate + observed` para sesiones vectorizadas existentes;
- `daily_synthesis + generated + processed` para reportes Markdown ya existentes.

`observed` no cuenta como procesado para saltar curacion. Es una marca de inventario.

## Comandos

Auditoria local:

```bash
python scripts/memory_audit.py
```

Backfill conservador:

```bash
python scripts/backfill_processing_catalog.py
```

Preflight de pipeline local:

```bash
python scripts/memory_pipeline_preflight.py
```

Preflight de pipeline local + remoto:

```bash
python ops/remote/kairos_remote.py memory-preflight --node laptop
```

JSON para comparar nodos desde tools:

```bash
python ops/remote/kairos_remote.py memory-preflight --node laptop --json
```

Preflight LAN completo:

```bash
python ops/remote/kairos_remote.py preflight --node laptop
```

JSON para tool futura:

```bash
python ops/remote/kairos_remote.py preflight --node laptop --json
```

## Que valida el preflight

- Git local/remoto.
- Python remoto y `fastembed`.
- Auditoria de memoria local.
- Auditoria de memoria remota.
- `/health`.
- estado de nodo.
- runtime normal.
- sync LAN.
- failover.
- smoke de escritura/visibilidad de memoria.

El smoke restaura `MEMORY.md` local al terminar para no dejar cambios de ordenamiento por la prueba.

## Riesgos restantes

- `memory_processing_catalog` no reemplaza una auditoria del contenido curado; solo evita repetir trabajos exactos.
- Si cambia el prompt de curacion, el hash de entrada cambia y la curacion se puede volver a ejecutar.
- El catalogo de candidatos no debe usarse como permiso para saltar LLM.
- Falta una auditoria profunda de calidad: comparar memorias extraidas contra sesiones fuente, detectar recuerdos redundantes y medir falsos positivos.

## Proximo corte recomendado

1. Correr `python ops/remote/kairos_remote.py memory-preflight --node laptop`.
2. Confirmar que el reporte termina con todos los nodos consistentes y revisar cualquier bloque `[DIFF]`.
3. Agregar un modo de auditoria de calidad para curaciones reales.
4. Separar embeddings remotos como servicio/job idempotente por hash.
