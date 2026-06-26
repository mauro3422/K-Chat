# Roadmap — Kairos distribuido entre PC grande y laptop

Fecha: 2026-06-26

## Norte

Kairos debe poder vivir en varias máquinas sin que el usuario tenga que pensar en qué proceso está haciendo cada cosa. En LAN primero, y más adelante fuera de casa con un transporte seguro.

La PC grande puede actuar como nodo pesado: memoria curada, embeddings, búsquedas, mantenimiento, backups y control operativo.

La laptop puede actuar como nodo liviano: UI, sesiones locales, uso en facultad, captura de conversación y consultas al nodo pesado cuando esté disponible.

## Principios

1. Las sesiones crudas siguen siendo locales por defecto, pero sus índices derivados pueden compartirse.
2. La memoria curada sigue siendo global y con un solo writer activo.
3. Los embeddings pesados deben poder delegarse al nodo grande.
4. La laptop no debe bloquearse ni degradarse por tareas de indexado caras.
5. La comunicación debe ser explícita, observable y recuperable.
6. El primer transporte robusto es SSH para operación y HTTP LAN para estado/eventos.
7. A futuro, el sistema debe poder reemplazar SSH por una tool/API propia sin cambiar el modelo mental.
8. Los roles deben ser móviles: si Mauro vive un mes en la laptop, la laptop puede volverse nodo principal temporal y la PC grande pasar a nodo remoto pesado cuando esté disponible.

## Decisión actual

Mantener `scripts/remote-kairos.ps1` solo como wrapper de emergencia/compatibilidad desde Windows.

Crear luego un subsistema real en:

```text
ops/remote/
```

Ese subsistema debería estar escrito en Python y modelar nodos, acciones, diagnósticos, perfiles y transporte.

## Topología inicial

### PC grande

- Rol preferido: `primary`
- Funciones:
  - escribir memoria curada;
  - procesar embeddings;
  - reconstruir `memory.db`;
  - ejecutar curator/gardener/tracer;
  - recibir snapshots de sesiones remotas;
  - operar backups;
  - coordinar failover.

### Laptop

- Rol preferido: `secondary`
- Funciones:
  - UI local;
  - sesiones propias;
  - captura de conversación;
  - cola local si no hay primaria;
  - delegar embeddings cuando la PC grande esté en LAN;
  - degradar a modo local si no hay red.

## Qué se comparte

- `MEMORY.md`
- `memory.db` como índice reconstruible, idealmente producido por el nodo pesado
- eventos de memoria, estado y UI
- snapshots resumidos de sesiones si el usuario lo habilita
- resultados de embeddings remotos
- configuración no secreta del usuario, layouts, widgets y objetos creados por la IA cuando tengan contrato propio

## Qué no se comparte por defecto

- `sessions.db` completo
- mensajes crudos sin consentimiento/contrato
- estado efímero de widgets local
- credenciales locales y `.env` completo
- bases SQLite abiertas por dos writers

## Configuración, secretos y objetos de usuario

`.env` no debe sincronizarse entero entre máquinas. Puede contener API keys, rutas locales, puertos, tokens y valores que no siempre significan lo mismo en Windows y Linux.

Lo correcto es separar:

- secretos: API keys, tokens, claves privadas;
- configuración local: rutas, puertos, nombre del servicio, entorno Python;
- configuración sincronizable: preferencias del usuario, layout de UI, widgets persistentes, objetos creados por la IA, opciones de visualización;
- estado efímero: panel abierto, scroll, selección temporal, modales, drag actual.

A futuro conviene una tabla o almacén específico para objetos configurables:

```text
user_objects / ui_objects / widget_objects
```

Ejemplos:

- layout de interfaz;
- paneles reordenables;
- widgets guardados;
- componentes tipo "legos" que la IA pueda mover, reconfigurar o reemplazar;
- presets de herramientas;
- preferencias por dispositivo.

Esto no debe mezclarse con `MEMORY.md` ni con `sessions.db`. Es otro plano: configuración viva del producto.

## Problema nuevo detectado

La laptop puede sufrir con embeddings o indexado en vivo cuando la conversación es larga o textual. Esto sugiere separar:

- persistencia local de sesión;
- extracción/snapshot de texto;
- cálculo de embeddings;
- almacenamiento de índices derivados.

La laptop puede conservar la sesión, pero pedirle a la PC grande que procese embeddings y devuelva:

- IDs vectorizados;
- resumen semántico;
- entidades;
- keywords;
- clusters;
- resultados de búsqueda.

En este documento, "snapshot" no significa copiar toda la base. Significa mandar un paquete chico y explícito con:

- `node_id`;
- `session_id`;
- `message_id` o rango;
- hash del contenido;
- texto normalizado o resumen, según política;
- timestamps;
- metadatos mínimos.

El nodo pesado puede usar eso para indexar sin apropiarse de la sesión cruda.

## Catálogo de embeddings y deduplicación

Mauro detectó una posible duplicación real: si ya se calcula un embedding durante una operación en vivo, después no debería recalcularse durante la síntesis o vectorización nocturna como si fuera texto nuevo.

Hay que introducir un catálogo/manifest de embeddings con identidad estable:

```text
embedding_manifest
```

Campos candidatos:

- `content_hash`
- `source_node_id`
- `source_kind`: `message`, `memory`, `summary`, `widget`, `object`
- `source_id`
- `model`
- `dimensions`
- `vector_store_id`
- `created_at`
- `updated_at`
- `status`: `ready`, `pending`, `stale`, `failed`

Regla:

1. Antes de generar un embedding, calcular `content_hash`.
2. Buscar si ya existe embedding compatible para `content_hash + model + dimensions`.
3. Si existe, reutilizarlo.
4. Si no existe, generarlo.
5. Si cambia el texto o cambia el modelo, marcarlo `stale` y recalcular.

Esto aplica tanto local como distribuido. Es probablemente una auditoría propia antes de diseñar el servicio remoto de embeddings.

## Fase 0 — Inventario y salud remota

Objetivo: dejar de depender de comandos sueltos.

Entregables:

- `ops/remote/nodes.json` local no versionado o `.example`;
- comando `doctor` por nodo;
- comando `pull` por nodo;
- comando `health` por nodo;
- reporte corto con causa probable.

Checklist:

- [x] Separar perfiles de nodos de variables `KAIROS_LINUX_*`.
- [x] Soportar más de un nodo.
- [x] Mantener `remote-kairos.ps1` como wrapper fino.
- [x] Crear cliente Python base.
- [ ] Registrar incompatibilidades de entorno como Python 3.14 + `lxml<6`.
- [x] Agregar `doctor`/`curita` base de compatibilidad: Python, servicios, repo y health.
- [ ] Ampliar `doctor` con pip, wheels, puertos, `.env` y permisos.

## Fase 1 — Cliente remoto Python

Objetivo: reemplazar el cerebro del `.ps1`.

Entregables:

- `ops/remote/kairos_remote.py`
- acciones: `list`, `doctor`, `health`, `pull`, `restart`, `logs`, `exec`, `chat`
- transporte SSH con timeout, batch mode y quoting robusto
- salida JSON opcional para que Kairos pueda consumirla como tool

Reglas:

- `exec` debe ser explícito y auditable.
- Las acciones peligrosas deben tener allowlist.
- Los errores deben decir nodo, acción y comando remoto.

## Fase 2 — Control bidireccional básico

Objetivo: que cualquiera de las dos máquinas pueda pedir estado o tareas a la otra.

Entregables:

- PC grande controla laptop por SSH.
- Laptop puede consultar salud/estado de PC grande por HTTP LAN.
- Definir si la laptop también tendrá llave SSH hacia la PC grande o solo API autenticada.
- Comando único para verificar ambos sentidos.

Preguntas abiertas:

- ¿Queremos SSH bidireccional o solo HTTP autenticado desde laptop hacia PC grande?
- ¿Qué acciones puede disparar la laptop sobre la PC grande?
- ¿Qué acciones quedan reservadas a Codex/operador?

Nota: una llave SSH no es cifrado de disco ni BitLocker. Es solo un par de claves para autenticarse entre máquinas y poder abrir una conexión remota sin escribir contraseña. Sirve para ejecutar comandos autorizados por SSH. No cifra el disco ni cambia el arranque del sistema.

Como todo es Kairos, no hay que pensar "PC grande manda siempre". Hay que pensar "nodo actual" y "nodo disponible". El control debe poder ir en ambos sentidos, con permisos distintos.

## Fase 3 — Servicio de embeddings remoto

Objetivo: que la laptop pueda delegar trabajo pesado a la PC grande.

Diseño inicial:

1. Laptop guarda sesión local.
2. Laptop detecta texto pendiente de vectorizar.
3. Laptop envía lote a PC grande por LAN.
4. PC grande calcula embeddings/keywords/entities.
5. PC grande devuelve resultado derivado.
6. Laptop marca el lote como procesado o queda en cola.

Entregables:

- endpoint o tool interna: `POST /api/node/embedding/jobs`
- cola local de trabajos pendientes
- idempotencia por hash de contenido
- límite de tamaño por lote
- fallback local opcional si no hay PC grande
- uso del `embedding_manifest` para no duplicar embeddings ya calculados en vivo

Reglas:

- No mover `sessions.db` completo.
- No bloquear la respuesta del chat por embeddings.
- No recalcular si el hash ya fue procesado.
- No tratar embeddings como descartables si ya se pagó el costo de calcularlos.

## Fase 4 — Índice global de sesiones, no sesiones globales

Objetivo: poder buscar “lo que pasó en la laptop” desde la PC grande sin mezclar bases crudas.

Idea:

- cada nodo publica un catálogo resumido de sesiones;
- la PC grande guarda un índice derivado;
- el contenido crudo queda en la máquina origen;
- si se necesita abrir detalle, se consulta al nodo origen.

Entregables:

- `session_snapshot` por nodo;
- resumen por sesión;
- embeddings generados en PC grande;
- referencias a `node_id + session_id + message_id`;
- endpoint para hidratar detalle desde el nodo dueño.
- manifest de embeddings por nodo para saber qué ya fue vectorizado.

## Fase 5 — Memoria curada global

Objetivo: que aprendizajes importantes de cualquier nodo lleguen a memoria común sin duplicación.

Flujo:

1. Nodo liviano propone memoria.
2. Nodo primario valida lease.
3. Nodo primario escribe `MEMORY.md` y `memory.db`.
4. Nodo primario emite evento `memory_write_completed`.
5. Nodo liviano actualiza estado local.

Esto ya existe parcialmente; falta endurecerlo con observabilidad y pruebas de campo repetibles.

## Fase 6 — Fuera de LAN

Objetivo: operar fuera de casa sin abrir SQLite ni confiar en IPs locales.

Opciones posibles:

- Tailscale/WireGuard como LAN virtual.
- HTTPS con autenticación por token/clave.
- relay propio mínimo.
- túnel temporal para mantenimiento.
- Syncthing para archivos elegidos, no para bases vivas multiwriter.

## Modos de conexión y desconexión

Kairos no puede comunicarse entre dos máquinas si no existe ningún canal físico o de red entre ellas. No hay forma de que la laptop llegue a la PC grande si está completamente aislada: sin Internet, sin LAN, sin hotspot compartido, sin cable, sin Bluetooth, sin Tailscale activo y sin ningún medio común.

Lo que sí se puede hacer es diseñar degradación elegante por niveles:

### Modo vivo por red local

Funciona aunque no haya Internet público, siempre que laptop y PC grande estén en la misma red o tengan un enlace directo.

Ejemplos:

- mismo WiFi aunque el router no tenga Internet;
- hotspot del celular compartido, incluso si no hay datos móviles, si ambos equipos se ven localmente;
- cable Ethernet directo;
- red ad-hoc/WiFi directo;
- USB networking/tethering local;
- Bluetooth PAN, lento pero posible.

En este modo, la laptop puede ser solo UI/terminal y la PC grande procesa modelos, embeddings, tools y búsquedas si la PC grande sí tiene Internet o acceso a modelos.

### Modo vivo por red privada externa

Funciona cuando hay Internet o algún camino externo que permita armar una red privada entre dispositivos.

Ejemplos:

- Tailscale;
- WireGuard;
- VPN propia;
- túnel temporal.

Para Kairos se parece a estar en LAN, pero pasando por Internet de forma segura.

### Modo carta / relay lógico

Este modo no exige una conexión viva permanente. La laptop escribe mensajes/intenciones en una cola local y los entrega cuando aparezca algún canal.

Ejemplo:

```text
laptop crea carta -> queda pendiente -> aparece red -> PC grande procesa -> escribe respuesta -> laptop la recibe cuando vuelva a sincronizar
```

Sirve para:

- cortes intermitentes;
- viajes;
- WiFi inestable;
- momentos donde la laptop no tiene modelos o Internet pero después recupera conexión.

No sirve para obtener respuesta instantánea si no hay ningún canal disponible. Sirve para no perder la intención, la sesión temporal ni el contexto.

### Modo aislado total

Si la laptop no puede hablar con la PC grande por ningún medio, Kairos debe seguir localmente en modo mínimo:

- guardar una sesión temporal;
- registrar mensajes;
- marcar trabajos pendientes;
- no prometer respuesta remota inmediata;
- oficializar y curar todo cuando vuelva el enlace.

## Syncthing, discovery y relay

Syncthing sincroniza archivos elegidos entre dispositivos. No ejecuta comandos y no reemplaza una API.

Syncthing necesita que los dispositivos puedan encontrarse por algún canal:

- en LAN puede descubrir pares localmente sin Internet;
- fuera de LAN normalmente necesita Internet para discovery/relay global o una configuración de direcciones conocidas;
- si ya existe Tailscale/WireGuard, puede sincronizar por esa red privada;
- si no hay ningún enlace, no puede sincronizar hasta que vuelva uno.

En Syncthing, "relay" significa un servidor intermediario que ayuda a pasar datos cuando dos dispositivos no pueden conectarse directo. Eso no es lo mismo que el "modo carta" de Kairos. El modo carta es una cola de mensajes; el relay de Syncthing es transporte de red.

Uso recomendado de Syncthing:

- `MEMORY.md` con cuidado y resolución de conflictos;
- backups;
- configs no secretas;
- carpetas `relay/inbox`, `relay/outbox`, `relay/results`;
- snapshots cerrados;
- manifiestos de embeddings;
- jobs JSON append-only.

Uso no recomendado:

- sincronizar `sessions.db` vivo;
- sincronizar `memory.db` vivo con dos writers;
- sincronizar `.env` completo;
- usarlo como garantía de respuesta en tiempo real.

Criterio:

- primero hacerlo sólido en LAN;
- después abstraer transporte;
- nunca acoplar memoria al transporte.

Explicación corta:

- Tailscale/WireGuard: crean una red privada entre tus dispositivos aunque estés fuera de casa. Para Kairos se parece a estar en LAN, pero pasando por Internet de forma segura.
- Syncthing: sincroniza archivos entre dispositivos. Puede funcionar sin Internet si ambos dispositivos están en la misma LAN o por enlace directo; fuera de eso necesita algún canal de descubrimiento/relay o una red privada como Tailscale. Es útil para `MEMORY.md`, configs no secretas o backups, pero no conviene para SQLite abierto por dos procesos.
- HTTPS propio: exponer una API de Kairos con autenticación. Más producto final, más responsabilidad de seguridad.
- Relay/túnel: puente temporal cuando no hay acceso directo.

## Fase 7 — Tool interna de Kairos

Objetivo: convertir el cliente remoto Python en herramienta del sistema.

Acciones candidatas:

- `remote_node_health(node)`
- `remote_node_pull(node)`
- `remote_node_restart(node)`
- `remote_node_logs(node, lines)`
- `remote_embedding_job(node, payload)`
- `remote_session_snapshot(node)`
- `remote_embedding_manifest(node, filters)`
- `remote_config_status(node)`

La tool debe devolver JSON estructurado, no texto libre.

## Deuda técnica registrada

- `scripts/remote-kairos.ps1` tiene quoting frágil para comandos complejos.
- `KAIROS_LINUX_*` no escala a múltiples nodos.
- `requirements.txt` fija `lxml<6`, pero la laptop con Python 3.14 tiene `lxml 6.1.1` por `searxng`; instalar requirements completo intenta compilar `lxml 5.x` y falla.
- `Update` remoto completo es demasiado rígido si `MEMORY.md` está sucio por curación local.
- Falta separar “actualizar código” de “actualizar dependencias” de “reiniciar”.
- Falta un plano claro para configuración sincronizable vs secretos locales.
- Falta auditar si la vectorización de sesiones recalcula embeddings ya generados durante operaciones en vivo.

## Próximo corte recomendado

1. Crear `ops/remote/`.
2. Mover el conocimiento del `.ps1` a un cliente Python mínimo.
3. Dejar `remote-kairos.ps1` llamando al cliente Python.
4. Agregar `nodes.example.json`.
5. Implementar `doctor`, `pull`, `health`, `restart`.
6. Usarlo para actualizar la laptop.
7. Recién después diseñar el servicio remoto de embeddings.
