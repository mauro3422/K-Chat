# Roadmap: puente LAN, memoria compartida y coordinación entre instancias

Fecha: 2026-06-19

Objetivo:

Construir un sistema local/LAN donde dos instancias de Kairos puedan colaborar sin duplicar trabajo, compartiendo memoria curada y eventos en tiempo real, pero manteniendo las sesiones locales separadas.

## Estado real verificado

Ya quedó implementado y probado en código:

- estado de nodo y rol primary/secondary;
- heartbeat y promoción/failover básico;
- bus de eventos LAN con notificación de memoria;
- cola persistente de escrituras de memoria;
- flush automático de memoria pendiente al arrancar como primaria;
- snapshot de memoria local/remota para diagnóstico;
- diagnóstico unificado de nodo/bridge/memoria;
- estado explícito de sync con cola, lease y frescura;
- healthcheck con sync y memoria serializados de forma segura;
- diagnóstico estructurado de conflictos de memoria con acciones sugeridas;
- failover con estado observable y anti-flapping básico;
- runbook operativo en la raíz con endpoints y criterios de salud;
- tests de coordinación y memoria asociados.

Sigue como deuda real:

- reflejar Telegram en ambas UIs sin duplicar persistencia;
- estado observability de reflejo de Telegram entre UI y LAN;
- observabilidad operativa más profunda para conflictos y failover;
- endurecer todavía más el failover para escenarios más hostiles;
- documentación operativa final y pruebas de integración más amplias.

## Idea central

La arquitectura no debe tratar a `memory.db` como una base compartida multiwriter entre dos máquinas.
La forma segura es:

- una instancia actúa como primaria para escritura de memoria y recepción de Telegram;
- la otra instancia actúa como secundaria/follower;
- ambas se comunican por LAN;
- ambas comparten memoria curada;
- cada una conserva sus propias sesiones;
- Telegram puede reflejarse en ambas UIs sin duplicar el bot.

## Principios

1. `MEMORY.md` es la fuente de verdad portable.
2. `memory.db` es memoria curada y reconstruible.
3. `sessions.db` es local por máquina.
4. Solo una instancia escribe memoria en cada momento.
5. La coordinación entre máquinas via LAN es para eventos, órdenes y presencia, no para escritura concurrente sobre SQLite.
6. Si hay conflicto, se resuelve por liderazgo, no por “dos writers a la vez”.

## Lo que ya existe y sirve como base

- `channels/telegram/adapter.py` ya puede notificar varias URLs web mediante `KAIROS_WEB_URL` separado por comas.
- `web/routers/events.py` expone `POST /api/events/notify` y `GET /api/events/stream`.
- `web/services/event_bus.py` resuelve pub/sub en memoria para una instancia.
- `src/tools/save_memory.py` ya contempla sincronización de `MEMORY.md` y conflictos de Syncthing.
- `docs/MEMORY_ARCHITECTURE.md` ya define que `MEMORY.md` es el source of truth y `memory.db` es reconstruible.

## Alcance del sistema

### Compartido

- `MEMORY.md`
- `memory.db`
- embeddings y memoria curada
- eventos de Telegram y eventos del sistema para refrescar UIs
- estado de “quién es primario”

### Local

- `sessions.db`
- mensajes crudos de cada sesión
- historial de cada instancia
- configuración local de proceso

## Arquitectura propuesta

### Capas

#### 1. Capa de liderazgo

Una sola instancia mantiene el rol de primaria.

Responsabilidades:

- recibir Telegram;
- escribir memoria curada;
- emitir eventos de sync a la otra instancia;
- resolver quién tiene el permiso de escritura;
- exponer estado de salud y liderazgo.

#### 2. Capa de follower

La instancia secundaria:

- recibe eventos por LAN;
- refresca UI y cache local;
- consulta memoria compartida;
- evita escribir memoria si no tiene el lock o el liderazgo;
- conserva sus propias sesiones.

#### 3. Capa de memoria compartida

Incluye:

- `MEMORY.md` sincronizado por filesystem compartido o Syncthing;
- `memory.db` como caché/índice reconstruible;
- embeddings y auxiliares derivados.

#### 4. Capa de sesiones locales

Cada máquina conserva:

- `sessions.db`;
- `messages`;
- `tool_calls`;
- `widget_states`;
- `debug_info`.

## Protocolo mínimo de coordinación

### Estado de líder

Cada instancia publica:

- `node_id`
- `hostname`
- `role`
- `heartbeat_at`
- `memory_revision`
- `uptime`

### Reglas

1. El líder activo es el único que escribe memoria.
2. Si el líder deja de emitir heartbeat por un TTL definido, el follower puede promoverse.
3. Si dos nodos creen ser líderes, se usa un lock/lease con expiración para resolver el conflicto.
4. El nodo que no tiene lease queda en modo read-only para memoria.

## Mecanismo sugerido

### Opción segura recomendada

Usar HTTP/WS sobre LAN para:

- heartbeats;
- eventos de sesión;
- notificaciones de memoria;
- estado de liderazgo.

Y usar Syncthing o carpeta compartida para:

- `MEMORY.md`;
- `memory.db` si se decide mantenerlo sincronizado, siempre con un solo escritor activo.

### Lo que no conviene

- dos procesos escribiendo el mismo `memory.db` al mismo tiempo;
- compartir `sessions.db` entre máquinas;
- depender de “confianza manual” para evitar duplicación;
- usar NFS/SMB como si fuera una DB multiwriter sin arbitraje.

## Fases del roadmap

### Fase 1 — Definir el contrato

Entregables:

- documento final de roles: primario, secundario, líder de memoria;
- definición de qué se comparte y qué queda local;
- definición del formato de heartbeat y lease.

Checklist:

- [x] Memoria compartida definida
- [x] Sesiones locales definidas
- [x] Telegram en primario definido
- [x] Política de failover definida

### Fase 2 — Canal de presencia LAN

Objetivo:

Detectar quién está vivo y quién manda.

Entregables:

- endpoint de heartbeat;
- estado de salud por nodo;
- TTL de líder;
- decisión de promoción.

Checklist:

- [x] `GET /health`
- [x] `POST /api/node/heartbeat`
- [x] `GET /api/node/state`
- [x] TTL configurado
- [x] Promoción/failover definido

### Fase 3 — Bus de eventos entre nodos

Objetivo:

Que una instancia notifique a la otra de eventos relevantes.

Eventos sugeridos:

- `memory_updated`
- `session_created`
- `session_deleted`
- `telegram_message`
- `leader_changed`
- `sync_started`
- `sync_completed`

Checklist:

- [x] Envío de eventos por LAN
- [x] Reintento con backoff
- [x] Fallback si el nodo remoto cae
- [x] Logs claros

### Fase 4 — Memoria compartida con un único escritor

Objetivo:

Centralizar la escritura de memoria curada.

Entregables:

- lease de escritura;
- escritura protegida por liderazgo;
- lectura segura desde ambas instancias;
- reconciliación de `MEMORY.md` y `memory.db`.

Checklist:

- [x] Solo el líder escribe `memory.db`
- [x] `MEMORY.md` se sincroniza
- [x] `memory.db` se reconstruye si hace falta
- [x] Conflictos detectados y resueltos

### Fase 5 — Telegram reflejado en ambas UIs

Objetivo:

Que lo que entra por Telegram aparezca en las dos máquinas, sin duplicar el bot.

Entregables:

- Telegram corriendo solo en la primaria;
- eventos emitidos a ambas UIs;
- refresco de sesiones/índices en la secundaria;
- sin escritura duplicada de mensajes.

Checklist:

- [x] Un solo bot activo
- [x] Broadcast a ambas UIs
- [x] No duplicar mensajes
- [x] No duplicar sesiones

### Fase 6 — Failover controlado

Objetivo:

Si la primaria cae, la secundaria puede tomar el rol.

Entregables:

- detección de caída;
- promoción automática o manual;
- reanudación limpia;
- checkpoint de memoria.

Checklist:

- [x] Heartbeat perdido detectado
- [x] Lease expirado
- [x] Promoción del follower
- [x] Re-sync al volver el nodo viejo

### Fase 7 — Optimización y seguridad

Objetivo:

Hacer el sistema robusto y fácil de operar.

Entregables:

- métricas de sincronización;
- alertas de conflicto;
- límites de rate;
- documentación operativa;
- scripts de diagnóstico.

Checklist:

- [x] Observabilidad básica
- [x] Diagnóstico de estado
- [x] Estado explícito de sync
- [x] Logs de sync
- [x] Documentación final

## Modelo operativo recomendado

### Opción manual

Una máquina se marca como primaria en un archivo/config.

Pros:

- simple;
- fácil de entender;
- rápido de implementar.

Contras:

- failover manual;
- menos automático.

### Opción automática

Heartbeat + lease + TTL.

Pros:

- failover real;
- mejor experiencia;
- menos intervención humana.

Contras:

- más compleja;
- requiere más pruebas.

## Recomendación práctica

Empezar por:

1. liderazgo manual;
2. sincronización de memoria compartida;
3. eventos LAN entre nodos;
4. failover automático después.

Eso te da valor rápido sin perder seguridad.

## Reglas de oro

- No compartir sesiones crudas.
- No escribir `memory.db` desde dos máquinas al mismo tiempo.
- No usar red como si fuera una base de datos distribuida.
- Sí usar LAN para coordinación y presencia.
- Sí usar Syncthing/carpeta compartida para memoria portable.
- Sí mantener Telegram en un solo nodo escritor.

## Criterio de listo

El sistema se considera bien resuelto cuando:

- una instancia es claramente primaria;
- la secundaria ve los eventos y la memoria compartida;
- Telegram aparece reflejado en ambas UIs;
- no hay duplicación de memoria ni de sesiones;
- el failover no rompe `memory.db`;
- `MEMORY.md` sigue siendo la verdad portable.
