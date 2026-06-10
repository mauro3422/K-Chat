# Arquitectura de `src/memory/`

## 1. Resumen de archivos

| Archivo | Qué hace |
|---------|----------|
| `__init__.py` | Re-exporta todo el API público del módulo memory |
| `database.py` | Gestiona conexiones SQLite con pool por hilo y ejecuta migraciones |
| `migrations.py` | Define 9 migraciones secuenciales del esquema |
| `sqlite_engine.py` | Implementación concreta del protocolo `DatabaseEngine` para SQLite |
| `repos/__init__.py` | Agrupa todos los repos en un dataclass `Repositories` y expone `get_repos()` |
| `repos/base.py` | Clase base `_BaseRepository` con manejo de conexión y transacciones |
| `repos/message_repository.py` | CRUD de mensajes (con tokens, reasoning, phases, tool_calls) |
| `repos/session_repository.py` | CRUD de sesiones + borrado en cascada de todas las tablas hijas |
| `repos/saved_widget_repository.py` | Widgets guardados con versionado (saved_widgets + widget_versions) |
| `repos/tool_call_repository.py` | Log de llamadas a herramientas por sesión |
| `repos/widget_state_repository.py` | Estado JSON de widgets por sesión (upsert) |
| `repos/debug_repository.py` | Info de debug por sesión (model, reasoning, system_prompt, etc.) |

---

## 2. `DatabaseEngine` Protocol

```python
class DatabaseEngine(Protocol):
    def connect(self) -> Any: ...
    def execute(self, conn, sql, params=()) -> Any: ...
    def commit(self, conn) -> None: ...
    def rollback(self, conn) -> None: ...
    def close(self, conn) -> None: ...
```

Es un **Protocol** (structural subtyping). Cualquier clase con esos 5 métodos es válida.
La única implementación es `SQLiteEngine` que envuelve `sqlite3`.

**Flujo en `database.py`:**
- Variable global `_engine: DatabaseEngine | None` permite inyectar un engine (testing/mocking).
- Si `_engine is None`, se usa `sqlite3` directamente (modo legacy).
- `get_conn()` retorna un `PooledConnection` cuyo `.close()` es no-op (la conexión se reutiliza por hilo via `threading.local`).
- `init_db()` ejecuta las migraciones pendientes leyendo `schema_version`.

---

## 3. Repository Pattern

```
_BaseRepository
├── MessageRepository
├── SessionRepository
├── ToolCallRepository
├── WidgetStateRepository
├── DebugRepository
└── SavedWidgetRepository
```

**`_BaseRepository`** provee:
- `_get_conn()`: retorna conexión inyectada o la del pool global.
- `_transaction()`: context manager que hace commit automático o rollback en error.

**Patrón de inyección:** Cada repo acepta `conn` y `engine` opcionales en `__init__`.
`get_repos(conn)` crea todos los repos compartiendo una misma conexión.

**Borrado en cascada:** `SessionRepository.delete()` orquesta borrado manual en todas las tablas hijas pasando el mismo cursor (sin transacciones anidadas).

---

## 4. Migraciones

- Array tupla `MIGRATIONS` con 9 funciones索引adas.
- `init_db()` lee `schema_version.version` (número entero, 0-based implícito).
- Ejecuta `MIGRATIONS[current:]` en orden, actualizando la versión tras cada una.
- Las migraciones 002-006 y 008 usan `ALTER TABLE ADD COLUMN` con `try/except OperationalError` (idempotentes).
- La migración 007 maneja migración de esquema viejo (rename + reinsert) o creación fresca.

**Esquema `schema_version`:** Tabla con una sola columna `version INTEGER` y una sola fila.

---

## 5. Tablas

| Tabla | PK | Datos | Relación |
|-------|----|-------|----------|
| `sessions` | `session_id TEXT` | name, created_at | — |
| `messages` | `id INTEGER AUTOINCREMENT` | session_id, role, content, model, reasoning, phases, tool_calls, tool_call_id, prompt/completion/total_tokens, created_at | FK → sessions |
| `tool_calls` | `id INTEGER AUTOINCREMENT` | session_id, tool_name, input, status, turn, created_at | FK → sessions |
| `debug_info` | `session_id TEXT` | model, reasoning, system_prompt, tool_calls (JSON), history_before (JSON), updated_at | FK → sessions |
| `widget_states` | `(session_id, widget_id)` | state (JSON), updated_at | FK → sessions |
| `saved_widgets` | `widget_id TEXT` | code, version, description, created_at, updated_at, session_id | FK → sessions |
| `widget_versions` | `(widget_id, version)` | code, description, created_at, session_id | FK → sessions |

**Índices** (migración 009): `idx_messages_session_id`, `idx_tool_calls_session_id`, `idx_saved_widgets_session_id`, `idx_widget_versions_session_id`.

---

## 6. Lo que está bien

- **Protocol para engine**: facilita testing con mocks sin herencia.
- **Conexión por hilo**: `threading.local` evita problemas de concurrencia SQLite.
- **Migraciones idempotentes**: `ALTER TABLE` con `try/except` permite re-ejecutar sin daño.
- **Borrado en cascada manual**: control explícito vs. `ON DELETE CASCADE` (más predecible).
- **Separación clara**: cada tabla tiene su repository con responsabilidad única.
- **Transacciones centralizadas**: `_transaction()` en base evita duplicar lógica de commit/rollback.
- **Widgets versionados**: tablas `saved_widgets` + `widget_versions` permiten historial completo.

---

## 7. Lo que podría mejorar

- **`schema_version` como tabla singular**: una sola fila es inusual; un schema más estándar sería `schema_version (version INTEGER PRIMARY KEY)`.
- **Foreign keys sin `ON DELETE`**: las FKs no definen comportamiento en cascada, dependiendo del borrado manual.
- **`PooledConnection` como wrapper frágil**: `__getattr__` delega todo al `_conn` subyacente, pero `.close()` es no-op — difícil de debugear si alguien llama `conn.close()` esperando que cierre.
- **Mezcla de estilos**: `SessionRepository.delete()` hace commit manualmente en vez de usar `_transaction()`.
- **`get_engine()` como global mutable**: el engine se inyecta vía variable global, no vía DI container.
- **No hay validación de esquema**: las migraciones no verifican integridad del esquema final.
- **Tipos `Any` en exceso**: `conn: Any` en todos los repos pierde type safety.
- **`init_db()` se llama en `get_conn()`**: cada conexión potencialmente re-ejecuta migraciones (aunque es idempotente, es overhead innecesario).
