# memory_search
**Busca en la memoria curada (memory.db) entradas que coincidan con un texto. Sirve para encontrar información guardada sobre el usuario, proyectos, preferencias, etc. Útil cuando no recordás exactamente qué se guardó.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `limit` | integer | No | 20 | Máximo de resultados a retornar (default: 20, max: 50). |
| `query` | string | Sí |  | Texto a buscar en las memorias (busca en key y value). |
