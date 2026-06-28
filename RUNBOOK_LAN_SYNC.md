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
- `GET /api/node/runtime` — estado operativo resumido: `normal`, `degraded` o `fallback`.
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
- `runtime.mode == normal`
- `sync.memory_is_fresh == true`
- `failover.should_promote == false` salvo caída real
- `telegram.has_recent_reflection == true` cuando hubo actividad reciente

## Nota

El objetivo no es tener dos escritores simultáneos.
El objetivo es que una instancia coordine, la otra acompañe y ambas vean el mismo estado curado sin duplicar persistencia.

## Prueba de campo recomendada entre dos PCs

Usala cuando quieras confirmar el sistema en vivo y no solo por tests.

### Prueba automatizada de dos nodos

Con ambos servidores levantados, corré desde cualquiera de las máquinas:

```bash
npm run smoke:lan -- http://192.168.1.40:8000
```

También podés configurarlo por entorno:

```bash
KAIROS_LAN_PRIMARY_URL=http://127.0.0.1:8000 KAIROS_LAN_SECONDARY_URL=http://192.168.1.40:8000 npm run smoke:lan
```

La prueba valida `/health`, `/api/node/state`, `/api/node/runtime`, heartbeats cruzados, `/api/node/sync/status`, `/api/node/failover/status` y una escritura de memoria de sonda visible desde el otro nodo. Por defecto limpia la sonda al final. Para opciones avanzadas, como ejecutar la promoción manual de la secundaria, usá el script directo:

```bash
python scripts/lan_field_smoke.py --primary-url http://127.0.0.1:8000 --secondary-url http://192.168.1.40:8000 --promote-secondary
```

Sin `--promote-secondary`, la prueba solo valida que el failover no pida promoción en estado sano.

### Diagnostico LAN de un solo comando

Para una mirada completa desde la PC grande hacia la laptop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote-kairos.ps1 -Action LanDoctor -HostName 192.168.1.40 -PrimaryUrl http://127.0.0.1:8000 -SecondaryUrl http://192.168.1.40:8000
```

Tambien se puede correr directo en Python:

```bash
python ops/remote/kairos_remote.py lan-doctor --node linux --primary-url http://127.0.0.1:8000 --secondary-url http://192.168.1.40:8000
```

`lan-doctor` junta en un reporte:

- git local;
- health/runtime local;
- doctor remoto por SSH + HTTP;
- smoke LAN no destructivo.

El reporte esta pensado para campo:

- si todo pasa, imprime una linea de resumen y `OK`;
- si algo falla, lista cada check roto con `detail`, `likely` y una muestra corta del JSON recibido;
- si las URLs estan invertidas, lo marca como error de topologia aunque los nodos respondan;
- si no queres tocar memoria durante un diagnostico, usa `--skip-write`.

Ejemplo de salida sana:

```text
LAN field smoke: 29/29 checks passed
OK: health, node state, heartbeats, sync, memory visibility and failover status passed.
```

### Antes de empezar

- Elegí una PC como primaria inicial.
- Asigná `KAIROS_NODE_ID` estable en ambas máquinas.
- Configurá `KAIROS_PEER_URLS` con la URL LAN de la otra PC.
- Confirmá que ambas máquinas pueden verse por red local.
- Reiniciá el servidor después de tocar `.env`.

### Secuencia de validación

1. Levantá la primaria y verificá:
   - `GET /health`
   - `GET /api/node/state`
   - `GET /api/node/runtime`
   - `GET /api/node/sync/status`
2. Levantá la secundaria y verificá que:
   - vea a la primaria en `cluster.states`
   - reporte `role=secondary`
   - mantenga `sessions.db` local
3. Hacé una escritura de memoria en la primaria.
4. Confirmá que:
   - se emita `memory_synced`
   - se emita `memory_write_completed`
   - la secundaria vea memoria fresca
5. Probá Telegram o un evento reflejado y revisá:
   - `GET /api/telegram/status`
   - `GET /api/events/stream`
6. Simulá caída de la primaria.
7. Confirmá que la secundaria:
   - detecta misses de heartbeat
   - puede promoverse si corresponde
   - no duplica sesiones ni memoria
8. Al volver la antigua primaria, verificá que:
   - no pisa al líder actual
   - la memoria se re-sincroniza sin conflicto

### Criterio de aprobado

- `health.status == ok`
- `runtime.mode == normal`
- `sync.memory_is_fresh == true`
- no hay doble escritura de memoria
- `sessions.db` sigue separado por máquina
- Telegram o el evento reflejado aparece en ambas UIs
- el failover no rompe la coordinación

### Comandos rápidos

Primaria:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/node/state
curl http://127.0.0.1:8000/api/node/runtime
curl http://127.0.0.1:8000/api/node/sync/status
curl http://127.0.0.1:8000/api/node/failover/status
```

Secundaria:

```bash
curl http://192.168.1.40:8000/health
curl http://192.168.1.40:8000/api/node/state
curl http://192.168.1.40:8000/api/node/runtime
curl http://192.168.1.40:8000/api/node/sync/status
curl http://192.168.1.40:8000/api/node/failover/status
curl http://192.168.1.40:8000/api/telegram/status
```

Prueba de memoria:

```bash
curl -X POST http://127.0.0.1:8000/api/memory/sync -H "Content-Type: application/json" -d '{"dry_run":false,"confirm":true,"key_pattern":"","fmt":"text"}'
curl -X POST http://127.0.0.1:8000/api/node/memory/flush
```

Prueba de failover:

```bash
curl -X POST http://192.168.1.40:8000/api/node/promote
curl http://192.168.1.40:8000/api/node/failover/status
```

Si usás otra IP o puerto, reemplazalos por la URL LAN real del nodo.

## Coordinación automática entre PCs

Para que los nodos se vean solos después de reiniciar, configurá en cada máquina:

- `KAIROS_NODE_ID`: un nombre estable, por ejemplo `mauro-pc` y `archlinux`.
- `KAIROS_PEER_URLS`: la URL del otro nodo, por ejemplo `http://192.168.1.40:8000` en la principal y `http://192.168.1.35:8000` en la secundaria.
- `KAIROS_NODE_HEARTBEAT_TTL`: dejalo en `15.0` salvo que quieras un timeout más largo.

Con eso, el arranque queda automático:

1. Hacés `git pull`.
2. Reiniciás el proceso en cada PC.
3. El nodo vuelve a mandar heartbeats al peer configurado.
4. `/health` y `/api/node/state` reflejan la relación sin tocar nada a mano.

Si cambiaste código, sí: `git pull` alcanza para traer la versión nueva, pero después hay que reiniciar el servidor para cargar el nuevo Python. Si solo cambiaste `.env`, también reiniciá para que tome la configuración.
