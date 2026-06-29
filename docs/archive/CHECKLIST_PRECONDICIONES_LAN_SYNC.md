# ✅ Checklist de precondiciones — puente LAN y memoria compartida (COMPLETADO)

Fecha: 2026-06-19 → Completado en v0.1.0/v0.2.0

> Nota: Todas las precondiciones de esta lista fueron satisfechas durante la implementación de LAN sync, federación de sesiones, y coordinación entre nodos (v0.0.64 → v0.2.0). Este documento se mantiene como referencia arquitectónica.

Objetivo:

Antes de programar la feature de coordinación entre dos máquinas por LAN, dejar cerradas estas precondiciones para evitar duplicación, corrupción de memoria y estados inconsistentes.

## 1. Definir roles sin ambigüedad

- [ ] Una sola instancia puede ser primaria en cada momento.
- [ ] La primaria es la única que escribe memoria curada.
- [ ] La secundaria solo lee, replica y recibe eventos.
- [ ] El cambio de rol está definido explícitamente.
- [ ] Existe una regla clara para elegir primaria inicial.

## 2. Separar con precisión qué se comparte y qué no

- [ ] `MEMORY.md` se comparte entre máquinas.
- [ ] `memory.db` se trata como índice/caché reconstruible.
- [ ] `sessions.db` queda local por máquina.
- [ ] Los mensajes y sesiones crudas no se sincronizan entre laptops.
- [ ] Telegram se refleja en ambas UIs, pero no duplica la persistencia.

## 3. Resolver el problema de escritura concurrente

- [ ] Definir un único writer para `memory.db`.
- [ ] Establecer un lock o lease de escritura.
- [ ] Definir TTL del lock/lease.
- [ ] Definir comportamiento si dos nodos creen ser primarios.
- [ ] Definir recuperación si el líder cae a mitad de escritura.

## 4. Confirmar que el transporte LAN está listo

- [ ] `HOST` puede bindearse a una IP accesible por LAN.
- [ ] `PORT` es configurable y no está hardcoded.
- [ ] El endpoint de eventos funciona fuera de `127.0.0.1`.
- [ ] Los dos nodos pueden verse por red local.
- [ ] Hay una URL/base configurable para cada nodo.

## 5. Tener un canal de eventos entre nodos

- [ ] Existe un endpoint para heartbeat.
- [ ] Existe un endpoint para notificar cambios de memoria.
- [ ] Existe un endpoint para notificar cambios de sesión/Telegram.
- [ ] Hay reintento con backoff si el nodo remoto no responde.
- [ ] Hay logging claro de eventos enviados y recibidos.

## 6. Proteger la memoria compartida

- [ ] `save_memory()` sigue siendo el único punto de escritura curada.
- [ ] Los conflictos de `MEMORY.md` están contemplados.
- [ ] `memory.db` puede reconstruirse desde `MEMORY.md`.
- [ ] Las embeddings y derivados no rompen si el nodo remoto cae.
- [ ] Se documenta qué pasa si Syncthing/FS compartido produce conflicto.

## 7. Aislar sesiones y estado episódico

- [ ] `sessions.db` sigue siendo local.
- [ ] Los IDs de sesión no se sincronizan entre máquinas.
- [ ] La UI secundaria puede mostrar eventos, pero no reclamar ownership de sesiones ajenas.
- [ ] El historial crudo no se mezcla entre nodos.

## 8. Evitar duplicación del bot de Telegram

- [ ] Solo una instancia corre Telegram como dueña del canal.
- [ ] La primaria emite los eventos a las dos UIs.
- [ ] La secundaria no levanta un segundo bot en paralelo.
- [ ] Hay fallback claro si Telegram cambia de primaria.

## 9. Definir la política de failover

- [ ] Si la primaria cae, la secundaria lo detecta.
- [ ] El tiempo de espera antes de promoverse está definido.
- [ ] La promoción automática o manual está decidida.
- [ ] Al volver la antigua primaria, no pisa la líder actual.
- [ ] Existe un mecanismo de re-sync posterior al failover.

## 10. Asegurar observabilidad mínima

- [ ] Logs de líder/seguidor.
- [ ] Logs de sync de memoria.
- [ ] Logs de eventos LAN.
- [ ] Logs de conflicto y recuperación.
- [ ] Un endpoint o comando de estado para inspección rápida.

## 11. Tener pruebas mínimas antes de escalar

- [ ] Prueba de “un solo writer”.
- [ ] Prueba de failover.
- [ ] Prueba de reflejo de Telegram en dos UIs.
- [ ] Prueba de que `sessions.db` no se comparte.
- [ ] Prueba de reconstrucción de `memory.db` desde `MEMORY.md`.

## 12. Criterio de entrada a implementación

No arrancar la feature completa hasta que esto esté confirmado:

- [ ] liderazgo definido
- [ ] memoria compartida definida
- [ ] sesiones locales definidas
- [ ] canal LAN operativo
- [ ] failover definido
- [ ] pruebas mínimas escritas o planificadas

## Decisión recomendada

Antes de programar la feature grande:

1. estabilizar roles;
2. fijar un solo writer;
3. validar el canal LAN;
4. recién después implementar coordinación completa.

