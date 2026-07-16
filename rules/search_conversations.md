# search_conversations
**Busca como grep en TODAS las conversaciones de sessions.db. Muestra las líneas donde aparece el texto con contexto alrededor (mensajes anteriores/posteriores). Útil para encontrar algo que se dijo sin recordar la sesión exacta.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `case_sensitive` | boolean | No | false | Si True, busca exactamente como se escribió (default: False = ignora mayúsculas) |
| `context` | integer | No | 1 | Mensajes de contexto alrededor de cada match (como grep -C). Default: 1, max: 3 |
| `max_matches` | integer | No | 20 | Máximo total de matches a mostrar (default: 20, max: 50) |
| `query` | string | Sí |  | Texto a buscar en los mensajes. Si querés buscar frase exacta, ponela entre comillas. |
| `role` | string | No | all | Filtrar por rol del mensaje: 'user', 'assistant', o 'all' (default: 'all') Values: all, user, assistant |
