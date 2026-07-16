# remember
**Actively recall related memories for the current chat. Use it when the user asks if you remember something, when a known entity appears with a memory/planning signal, or when you need to link a new candidate to prior memories.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `contradiction_score` | number | No | 0.0 | Optional contradiction signal for link recommendation. |
| `entity_overlap` | number | No | 0.0 | Optional entity overlap signal for link recommendation. |
| `intent` | string | No | recall | auto only searches when policy triggers; recall/link/verify perform the search and add intent-specific guidance. Values: auto, recall, link, verify |
| `keyword_overlap` | number | No | 0.0 | Optional keyword overlap signal for link recommendation. |
| `known_entities` | array | No | [] | Known entities detected in the message. |
| `limit` | integer | No | 5 | Maximum recall results (default: 5, max: 20). |
| `min_score` | number | No | 0.2 | Minimum recall score. |
| `query` | string | Sí |  | What to remember or connect. |
| `record_event` | boolean | No | true | Persist a JSONL recall event for later curation. |
| `semantic_score` | number | No | 0.0 | Optional semantic similarity signal for link recommendation. |
| `source` | string | No |  | Filter by memory source, or empty for all layers. Values: , memory, session, session_summary, transversal_synthesis, memory_candidate, memory_inbox |
