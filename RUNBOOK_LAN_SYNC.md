# Runbook operativo — LAN, memoria y failover

Este documento resume cómo operar el estado actual del sistema entre dos instancias de Kairos sin perder de vista qué está compartido y qué queda local.

## Qué comparte el sistema

- `MEMORY.md` como fuente de verdad curada.
- `memory.db` como índice reconstruible.
- eventos de UI y Telegram por LAN.
- estado de coordinación: primary/secondary, heartbeat, sync y failover.

## Qué sigue local

- `sessions.db`
- historial crudo de cada máquina
- procesos y configuración de cada nodo

## Endpoints útiles

- `GET /health` — salud general con coordinación, sync y failover.
- `GET /api/node/state` — estado local del nodo.
- `GET /api/node/diagnostics` — diagnóstico unificado de nodo, bridge y memoria.
- `GET /api/node/sync/status` — cola, lease y frescura de memoria.
- `GET /api/node/failover/status` — estado observable de failover.
- `GET /api/memory/status` — cola y lease de memoria.
- `GET /api/memory/diagnostics` — comparación memoria.md vs memory.db.
- `GET /api/memory/conflicts` — resumen accionable de conflictos.
- `GET /api/telegram/status` — estado de reflejo de Telegram.

## Flujo normal

1. La primaria recibe escrituras de memoria.
2. La secundaria pide aprobación y, si no hay primaria disponible, encola.
3. Si la primaria vuelve, la cola se reintenta y se reinyecta.
4. Los eventos de Telegram se reflejan por bus local y LAN.
5. El failover monitorea heartbeat y solo promueve tras misses consecutivos.

## Qué mirar cuando algo huele raro

- Si la memoria no avanza:
  - revisar `/api/node/sync/status`
  - revisar `/api/memory/conflicts`
  - revisar `/api/memory/status`

- Si el failover quedó dudoso:
  - revisar `/api/node/failover/status`
  - revisar `/health`
  - revisar si el lease de liderazgo está ocupado

- Si Telegram no se refleja:
  - revisar `/api/telegram/status`
  - revisar `/api/events/stream`
  - revisar logs del bot y del bridge LAN

## Arranque recomendado

1. Levantar una instancia primaria.
2. Verificar `GET /health`.
3. Confirmar `GET /api/node/state`.
4. Desde la secundaria, verificar `GET /api/node/sync/status` y `GET /api/node/failover/status`.
5. Probar un mensaje de Telegram y confirmar `GET /api/telegram/status`.

## Criterio de operación sana

- `health.status == ok`
- `sync.memory_is_fresh == true`
- `failover.should_promote == false` salvo caída real
- `telegram.has_recent_reflection == true` cuando hubo actividad reciente

## Nota

El objetivo no es tener dos escritores simultáneos.
El objetivo es que una instancia coordine, la otra acompañe y ambas vean el mismo estado curado sin duplicar persistencia.
