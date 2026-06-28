# Servicio remoto de embeddings LAN

Fecha: 2026-06-28

## Objetivo

Permitir que la laptop delegue trabajo pesado de embeddings a la PC grande cuando ambas estan conectadas por LAN o por una red privada tipo Tailscale.

La laptop conserva sus sesiones locales. La PC grande procesa lotes derivados y devuelve resultados indexables.

## Regla central

La unidad idempotente es el hash de contenido, no el mensaje suelto ni la sesion completa.

Si el hash ya existe en el catalogo, no se recalcula.

## Flujo propuesto

1. Laptop guarda mensajes en `sessions.db` local.
2. Vectorizer detecta intercambios pendientes.
3. Laptop arma lote con `node_id`, `session_id`, `exchange_idx`, texto limitado y `content_hash`.
4. PC grande recibe el job.
5. PC grande descarta hashes ya procesados.
6. PC grande calcula embeddings/keywords/entities para lo nuevo.
7. PC grande devuelve `content_hash -> resultado`.
8. Laptop guarda solo resultados derivados y marca catalogo local.

## Contrato inicial

Endpoint futuro:

```text
POST /api/node/embedding/jobs
```

Payload:

```json
{
  "source_node_id": "pc-secundaria",
  "job_id": "uuid-or-hash",
  "items": [
    {
      "session_id": "local-session-id",
      "exchange_idx": 12,
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
  "processed": 1,
  "deduped": 0,
  "failed": 0,
  "items": [
    {
      "content_hash": "abc123",
      "status": "embedded",
      "remote_vec_rowid": 1234
    }
  ]
}
```

## Que no debe hacer

- No copiar `sessions.db` completo.
- No compartir `.env`.
- No abrir SQLite con dos writers.
- No bloquear el chat esperando embeddings remotos.
- No asumir que la PC grande siempre esta disponible.

## Fallback

Si la PC grande no responde:

- la laptop deja el job en cola local;
- el chat sigue funcionando;
- el preflight debe mostrar cola pendiente;
- al volver LAN/Tailscale, se reintenta por hash.

## Relacion con los catalogos actuales

- `memory_work_catalog`: sigue siendo el catalogo de vectorizacion por item.
- `memory_processing_catalog`: sigue siendo el catalogo de etapas semanticas posteriores.
- El servicio remoto debe escribir una marca equivalente a `embedded`/`deduped` y nunca inventar curaciones.

## Corte tecnico siguiente

1. Extraer DTOs de job/result en un modulo puro.
2. Agregar cola local de jobs pendientes.
3. Agregar endpoint HTTP autenticado solo para LAN/Tailscale.
4. Probar con lote de 1 item y hash ya existente.
5. Integrarlo al preflight como `remote_embedding_job_dry_run`.
