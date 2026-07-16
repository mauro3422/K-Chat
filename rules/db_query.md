# db_query
**Consulta SQLite del sistema en modo solo lectura. Soporta sessions.db (chats, tools, widgets), memory.db (memoria curada), y deleted_sessions.db (sesiones eliminadas).**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `columns` | string | No |  | Columnas a mostrar separadas por coma (default: columnas útiles según tabla). Usar substr(col,1,N) para truncar. |
| `limit` | integer | No | 10 | Máximo de filas a retornar (default: 10, max: 50) |
| `order_by` | string | No |  | Columna para ordenar (default: auto según tabla) |
| `order_dir` | string | No | DESC | Dirección de orden (default: DESC) Values: ASC, DESC |
| `search` | string | No |  | Buscar texto en las columnas de contenido de la tabla (LIKE). Ej: 'sqlite', 'embeddings%'. No necesita '%' alrededor, se agrega automáticamente. |
| `session_id` | string | No |  | Filtrar por session_id (opcional). Usar '%' como wildcard para búsqueda parcial. |
| `table` | string | Sí |  | Tabla a consultar. Segun la tabla, se conecta a sessions.db, memory.db o deleted_sessions.db automaticamente. Values: chat_journal, debug_info, deleted_sessions, gateway_log, memory_index, messages, saved_widgets, sessions, tool_calls, widget_states, widget_versions |
| `where` | string | No |  | Filtro WHERE personalizado (opcional). Solo columnas simples y valores con ?, parámetros en where_params. Ej: 'role = ? AND content LIKE ?' |
| `where_params` | string | No |  | Parámetros para el WHERE, separados por coma. Ej: 'user,%hola%' |
