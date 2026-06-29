# Estado actual del plan LAN

Fecha: 2026-06-19

## Ya quedó implementado

- estado de nodo y liderazgo local;
- endpoints de nodo para estado, heartbeat, promote/demote;
- health compatible con tests y con chequeo de DB en runtime;
- puente LAN de heartbeats entre peers;
- propagación de eventos LAN a peers;
- recepción local de eventos en `/api/node/event`;
- tests focalizados para el puente LAN y el nodo;
- estado de coordinación y memoria expuesto en `/health` para diagnóstico;
- estado explícito de sync expuesto en `/api/node/sync/status` y en `/health`;
- diagnóstico estructurado de conflictos de memoria con resumen y acciones;
- liderazgo con lease para evitar split-brain básico;
- cola persistente de escrituras de memoria para secundarios;
- failover automático básico de secundaria a primaria;
- failover con observabilidad y umbral anti-flapping;
- runbook operativo en la raíz con endpoints y criterios de salud;
- Telegram bloqueado en nodos secundarios cuando hay clúster;
- marcas de revisión/sync de memoria en el coordinador para auditar frescura;
- compare/repair/sync de memoria con diff único y tests directos;
- sincronización y repair HTTP ahora solo marcan estado cuando hubo cambios reales;
- las rutas de memoria emiten `memory_synced` de forma consistente tras aplicar cambios;
- repair ahora sugiere candidatos de renombre y usa el valor de `MEMORY.md` al resolverlos;
- las escrituras de memoria ahora emiten `memory_write_queued` y `memory_write_completed`;
- la UI muestra aviso cuando una memoria queda en cola o termina de sincronizarse.
- al arrancar como primaria, la app re-aplica automáticamente la cola persistida de memoria.
- los eventos LAN de memoria ya actualizan la frescura local al recibirse en `/api/node/event`.

## Estado final verificado

No queda deuda bloqueante del plan LAN/memoria/failover.

Lo que puede quedar como afinamiento opcional, si se quiere seguir puliendo más adelante, ya no impide operar:

- métricas más finas;
- alertas externas;
- integración viva entre dos máquinas físicas adicionales para prueba de campo.
