# recall_memories
**Search your memory for anything related to a query. Uses hybrid search (semantic + keywords + entities) so it finds conceptually related memories even if the exact words do not match.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `include_graph_context` | boolean | No | false | Include related entity graph context when repositories are available. |
| `known_entities` | array | No | [] | Known entities already detected in the current turn. |
| `limit` | integer | No | 5 | Maximum number of results (default: 5, max: 20). |
| `min_score` | number | No | 0.2 | Minimum fusion score (0.0 to 1.0). Default: 0.2. |
| `query` | string | Sí |  | The query to search for in memory. |
| `source` | string | No |  | Filter by source: canon memory, sessions, summaries, transversal synthesis, memory candidates, or empty for all. Values: , memory, session, session_summary, transversal_synthesis, memory_candidate, memory_inbox |
