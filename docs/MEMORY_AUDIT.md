# Auditoría de `src/memory/`

## 1. Qué cubre

Este bloque concentra:
- resolución de ruta DB
- conexión SQLite por hilo
- estado global del engine inyectable
- bootstrap del esquema
- migraciones
- repositorios persistentes

## 2. Corte de responsabilidades actual

- [`src/memory/db_path.py`](/home/maurol/dev/K-Chat/src/memory/db_path.py) resuelve la ruta efectiva de la DB.
- [`src/memory/engine_state.py`](/home/maurol/dev/K-Chat/src/memory/engine_state.py) guarda el engine activo.
- [`src/memory/lifecycle.py`](/home/maurol/dev/K-Chat/src/memory/lifecycle.py) guarda qué rutas ya fueron inicializadas.
- [`src/memory/connection_pool.py`](/home/maurol/dev/K-Chat/src/memory/connection_pool.py) maneja la conexión por hilo y el reset cuando cambia la ruta.
- [`src/memory/schema.py`](/home/maurol/dev/K-Chat/src/memory/schema.py) ejecuta bootstrap + migraciones.
- [`src/memory/migrations.py`](/home/maurol/dev/K-Chat/src/memory/migrations.py) define el esquema evolutivo.
- [`src/memory/repos/`](/home/maurol/dev/K-Chat/src/memory/repos/) encapsula la persistencia por tabla.

## 3. Puntaje

- Desacople del bloque de memoria: **8.4/10**
- Contratos y límites: **8.6/10**
- Robustez ante regresiones: **8.3/10**
- Legibilidad operativa: **8.1/10**

## 4. Lo que está bien

- La DB ya no vive en un módulo monolítico.
- El engine es intercambiable por protocolo.
- El estado de inicialización salió de `schema.py` y dejó de ser un detalle privado.
- `get_conn()` invalida la conexión cacheada cuando cambia la ruta.
- Los repositorios siguen siendo la frontera correcta para la lógica de negocio de persistencia.

## 5. Riesgos que todavía quedan

| Riesgo | Impacto | Estado |
|---|---|---|
| `get_engine()` global mutable | Medio | Aceptable, pero sigue siendo un punto compartido |
| Bootstrap + migraciones juntos en `schema.py` | Medio | Funciona, pero sigue siendo una pieza cargada |
| `PooledConnection.close()` no-op | Medio | Correcto para el pool, pero puede confundir al caller |
| `SessionRepository.delete()` sigue orquestando cascada manual | Bajo/medio | Intencional, aunque acoplado |
| `Any` en repositorios | Bajo | Reduce type safety |

## 6. Qué no romper

1. `get_conn()` debe seguir devolviendo una conexión reutilizable por hilo.
2. Cambiar `MEMORY_DB_PATH` debe invalidar la conexión vieja.
3. `init_db_for_path()` debe seguir siendo idempotente por ruta.
4. Las migraciones deben seguir siendo seguras al re-ejecutarse.
5. Los repos no deben requerir que el caller conozca tablas hijas.

## 7. Regresión que cubre el borde más delicado

- [`tests/unit/test_database.py`](/home/maurol/dev/K-Chat/tests/unit/test_database.py)
- Nuevo caso: al cambiar la ruta DB, la conexión cacheada anterior se cierra y se crea una nueva.

## 8. Próximo corte razonable

Si se quiere seguir bajando acople, el siguiente paso útil es:
1. Separar el bootstrap de `schema.py` en un módulo de lifecycle/bootstrap más explícito.
2. Quitar el `get_engine()` global con una inyección más formal.
3. Tipar mejor `conn`/`engine` en repositorios.
