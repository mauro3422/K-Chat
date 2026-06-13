# db_query
**Consulta la base de datos SQLite del sistema en modo solo lectura. Útil para debuggear sesiones, mensajes, tools, widgets, etc. Soporta filtrado por session_id, orden y límite.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `columns` | string | No |  | Columnas a mostrar separadas por coma (default: columnas útiles según tabla) |
| `limit` | integer | No | 10 | Máximo de filas a retornar (default: 10, max: 50) |
| `order_by` | string | No |  | Columna para ordenar (default: auto según tabla) |
| `order_dir` | string | No | DESC | Dirección de orden (default: DESC) Valores: ASC, DESC |
| `session_id` | string | No |  | Filtrar por session_id (opcional). Usar '%' como wildcard para búsqueda parcial. |
| `table` | string | Sí |  | Tabla a consultar Valores: debug_info, memory_index, messages, saved_widgets, sessions, tool_calls, widget_states, widget_versions |
