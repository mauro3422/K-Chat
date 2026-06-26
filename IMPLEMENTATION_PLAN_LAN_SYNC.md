# ✅ Plan de implementación — puente LAN y memoria compartida (COMPLETADO)

Fecha: 2026-06-19 → Completado en v0.1.0/v0.2.0

> Nota: Este plan fue ejecutado en su totalidad. Ver ROADMAP_DISTRIBUTED_KAIROS.md para el estado actual de la arquitectura distribuida.

Objetivo:

Implementar coordinación entre dos instancias de Kairos por LAN, compartiendo memoria curada y eventos, manteniendo sesiones locales separadas y evitando duplicación.

## Prioridad general

1. Estabilizar la coordinación.
2. Definir liderazgo.
3. Exponer el canal LAN.
4. Compartir memoria curada.
5. Reflejar Telegram y eventos en ambas UIs.
6. Agregar failover.

---

## Fase 0 — Preparación y contratos

### Meta

Dejar explícito qué se comparte, qué se replica y qué queda local.

### Archivos a revisar/tocar

- [docs/MEMORY_ARCHITECTURE.md](C:/Dev/Kairos/docs/MEMORY_ARCHITECTURE.md)
- [docs/ARCHITECTURE.md](C:/Dev/Kairos/docs/ARCHITECTURE.md)
- [docs/ARCHITECTURE_SUMMARY.md](C:/Dev/Kairos/docs/ARCHITECTURE_SUMMARY.md)
- [docs/TELEGRAM.md](C:/Dev/Kairos/docs/TELEGRAM.md)
- [src/memory/repos_memory/__init__.py](C:/Dev/Kairos/src/memory/repos_memory/__init__.py)
- [src/memory/repos/session_repository.py](C:/Dev/Kairos/src/memory/repos/session_repository.py)
- [channels/telegram/adapter.py](C:/Dev/Kairos/channels/telegram/adapter.py)

### Tareas

- [ ] Reafirmar que `MEMORY.md` es la fuente de verdad.
- [ ] Reafirmar que `memory.db` es índice/caché reconstructible.
- [ ] Reafirmar que `sessions.db` no se comparte.
- [ ] Reafirmar que Telegram se refleja, pero no se duplica.
- [ ] Definir lenguaje de liderazgo: primaria / secundaria / follower.

### Criterio de salida

- Contratos escritos y consistentes en docs.
- No hay ambigüedad sobre qué se comparte.

---

## Fase 1 — Liderazgo y estado de nodo

### Meta

Tener una instancia primaria clara y un mecanismo para saber si sigue viva.

### Archivos probables

- [src/gateway.py](C:/Dev/Kairos/src/gateway.py)
- [web/app_factory.py](C:/Dev/Kairos/web/app_factory.py)
- [web/routers/health.py](C:/Dev/Kairos/web/routers/health.py)
- [web/routers/events.py](C:/Dev/Kairos/web/routers/events.py)
- [src/config_loader.py](C:/Dev/Kairos/src/config_loader.py)

### Tareas

- [ ] Agregar o formalizar `node_id`.
- [ ] Definir `role` del nodo: primary / secondary.
- [ ] Exponer heartbeat de nodo.
- [ ] Agregar TTL de liderazgo.
- [ ] Definir promoción si la primaria desaparece.

### Criterio de salida

- Una instancia sabe si es líder.
- La otra sabe que es follower.

---

## Fase 2 — Canal LAN de eventos

### Meta

Que dos máquinas se puedan notificar eventos entre sí sin compartir sesiones.

### Archivos probables

- [web/routers/events.py](C:/Dev/Kairos/web/routers/events.py)
- [web/services/event_bus.py](C:/Dev/Kairos/web/services/event_bus.py)
- [channels/telegram/adapter.py](C:/Dev/Kairos/channels/telegram/adapter.py)
- [channels/telegram/ws_client.py](C:/Dev/Kairos/channels/telegram/ws_client.py)
- [src/gateway.py](C:/Dev/Kairos/src/gateway.py)

### Tareas

- [ ] Definir payload estándar de eventos LAN.
- [ ] Crear envío de heartbeat entre nodos.
- [ ] Crear notificación de `memory_updated`.
- [ ] Crear notificación de `telegram_message`.
- [ ] Crear notificación de `leader_changed`.
- [ ] Agregar reintentos con backoff.

### Criterio de salida

- Un nodo puede avisarle al otro que cambió algo.
- La UI remota puede refrescar sin duplicar persistencia.

---

## Fase 3 — Memoria compartida como único writer

### Meta

Permitir aprendizaje compartido diario sin corrupción ni doble escritura.

### Archivos probables

- [src/tools/save_memory.py](C:/Dev/Kairos/src/tools/save_memory.py)
- [src/memory/repos_memory/memory_index_repo.py](C:/Dev/Kairos/src/memory/repos_memory/memory_index_repo.py)
- [src/memory/repos_memory/__init__.py](C:/Dev/Kairos/src/memory/repos_memory/__init__.py)
- [src/memory/memory_schema.py](C:/Dev/Kairos/src/memory/memory_schema.py)
- [src/memory/memory_db_path.py](C:/Dev/Kairos/src/memory/memory_db_path.py)
- [src/memory/operations/sync.py](C:/Dev/Kairos/src/memory/operations/sync.py)

### Tareas

- [ ] Definir un solo writer para `memory.db`.
- [ ] Implementar lease/lock para escritura.
- [ ] Mantener `save_memory()` como punto canónico.
- [ ] Resolver conflicto de `MEMORY.md`.
- [ ] Confirmar reconstrucción de `memory.db` desde `MEMORY.md`.

### Criterio de salida

- Solo una máquina escribe memoria curada.
- La otra consume y replica.

---

## Fase 4 — Telegram en una sola primaria, reflejo en ambas

### Meta

Que el bot viva una vez, pero lo que reciba se vea en dos UIs.

### Archivos probables

- [channels/telegram/bot.py](C:/Dev/Kairos/channels/telegram/bot.py)
- [channels/telegram/adapter.py](C:/Dev/Kairos/channels/telegram/adapter.py)
- [channels/telegram/ws_client.py](C:/Dev/Kairos/channels/telegram/ws_client.py)
- [web/routers/events.py](C:/Dev/Kairos/web/routers/events.py)
- [web/src_ts/app_mock.ts](C:/Dev/Kairos/web/src_ts/app_mock.ts)
- [web/src_ts/core/session/SessionStore.ts](C:/Dev/Kairos/web/src_ts/core/session/SessionStore.ts)

### Tareas

- [ ] Asegurar que solo la primaria corre Telegram.
- [ ] Emitir eventos al resto de nodos por LAN.
- [ ] Reflejar mensajes en ambas UIs.
- [ ] Evitar doble persistencia de mensajes.
- [ ] Mantener sesiones locales.

### Criterio de salida

- Telegram entra una sola vez.
- Dos pantallas lo ven.
- No hay duplicación de sesiones.

---

## Fase 5 — Failover

### Meta

Permitir que la secundaria tome el rol si la primaria cae.

### Archivos probables

- [src/gateway.py](C:/Dev/Kairos/src/gateway.py)
- [web/routers/health.py](C:/Dev/Kairos/web/routers/health.py)
- [web/routers/events.py](C:/Dev/Kairos/web/routers/events.py)
- [src/tools/manage_memory.py](C:/Dev/Kairos/src/tools/manage_memory.py)

### Tareas

- [ ] Definir TTL de heartbeat.
- [ ] Detectar caída de líder.
- [ ] Promover secundaria.
- [ ] Evitar split-brain.
- [ ] Reconciliar al volver la máquina vieja.

### Criterio de salida

- Si se cae una máquina, la otra no se rompe.
- La coordinación sigue viva.

---

## Fase 6 — Observabilidad y diagnóstico

### Meta

Poder ver qué nodo manda, qué se compartió y qué falló.

### Archivos probables

- [src/gateway_log.py](C:/Dev/Kairos/src/gateway_log.py)
- [web/routers/debug.py](C:/Dev/Kairos/web/routers/debug.py)
- [web/routers/logbus.py](C:/Dev/Kairos/web/routers/logbus.py)
- [docs/HEALTH.md](C:/Dev/Kairos/docs/HEALTH.md)

### Tareas

- [ ] Logs de liderazgo.
- [ ] Logs de heartbeat.
- [ ] Logs de sync de memoria.
- [ ] Logs de eventos LAN.
- [ ] Endpoint de estado para inspección.

### Criterio de salida

- Se puede diagnosticar una desincronización sin adivinar.

---

## Fase 7 — Pruebas

### Meta

Probar que el diseño evita duplicación y mantiene memoria compartida.

### Archivos probables

- [tests/unit/test_anti_regression.py](C:/Dev/Kairos/tests/unit/test_anti_regression.py)
- [tests/unit/test_app_factory.py](C:/Dev/Kairos/tests/unit/test_app_factory.py)
- [tests/unit/test_message_persister.py](C:/Dev/Kairos/tests/unit/test_message_persister.py)
- [tests/unit/web/services/test_chat_stream.py](C:/Dev/Kairos/tests/unit/web/services/test_chat_stream.py)
- nuevos tests de sync/LAN

### Tareas

- [ ] Prueba de un solo writer.
- [ ] Prueba de heartbeat.
- [ ] Prueba de failover.
- [ ] Prueba de reflejo de Telegram.
- [ ] Prueba de reconstrucción de memoria.

### Criterio de salida

- El sistema queda probado antes de ampliar alcance.

---

## Orden recomendado de implementación

1. Fase 0 — contratos.
2. Fase 1 — liderazgo y estado de nodo.
3. Fase 2 — canal LAN de eventos.
4. Fase 3 — memoria compartida con único writer.
5. Fase 4 — Telegram reflejado en ambas.
6. Fase 5 — failover.
7. Fase 6 — observabilidad.
8. Fase 7 — pruebas finales.

## Regla de decisión

No arrancar la implementación grande hasta que estén claros:

- el rol primario;
- el canal LAN;
- el único writer de memoria;
- el aislamiento de sesiones;
- el criterio de failover.

