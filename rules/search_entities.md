# search_entities
**Search the entity knowledge graph for people, projects, technologies, etc.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `entity_type` | string | No |  | Filter by entity type (optional). Values: , persona, proyecto, tecnologia, lenguaje, tema, lugar |
| `limit` | integer | No | 10 | Maximum results (default: 10, max: 50). |
| `query` | string | Sí |  | Entity name or keyword to search for. |
